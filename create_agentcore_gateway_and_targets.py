
import os
import sys
import logging
from typing import Dict, Any

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bedrock_agentcore_starter_toolkit import Runtime 

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from streamable_http_sigv4 import streamablehttp_client_with_sigv4
import boto3
import json

####################################################################################
import os
import sys

if "__file__" in globals():
    current_dir = os.path.dirname(os.path.abspath(__file__))
else:
    current_dir = os.getcwd()

# Navigate up one level to access the shared utils module
# The utils.py file contains helper functions used across multiple tutorials
utils_dir = os.path.abspath(os.path.join(current_dir, ".."))

# Add the utils directory to Python's module search path
# This allows us to import utils from the parent directory
sys.path.insert(0, utils_dir)

# Import the utils module which contains helper functions for gateway management
import utils


from bedrock_agentcore_starter_toolkit import Runtime 
# from bedrock_agentcore_starter_toolkit.operations.runtime import destroy_bedrock_agentcore
from deploy_cloudformation import deploy_stack, delete_stack
# from pathlib import Path
from strands import Agent  
from strands.models import BedrockModel  
from strands.tools.mcp.mcp_client import MCPClient 
from streamable_http_sigv4 import streamablehttp_client_with_sigv4  
import boto3  
# import getpass 
import json
import logging  
import uuid 

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


session = boto3.Session()

credentials = session.get_credentials()

region = session.region_name

cf_client = boto3.client(
    "cloudformation", region_name=region
)

agentcore_client = boto3.client(
    "bedrock-agentcore-control",
    region_name=region,
)

identity_client = boto3.client(
    "bedrock-agentcore-control",
    region_name=region,
)

s3_client = session.client('s3')

sts_client = session.client('sts')
account_id = sts_client.get_caller_identity()["Account"]


# Define configuration variables for the tutorial resources

# CloudFormation stack configuration
stack_name = "customer-support-lambda-stack-new7"  # Name of the stack that creates Lambda and DynamoDB
template_file = "customer_support_lambda.yaml"  # Path to CloudFormation template

# Gateway and target names
gateway_name = "customer-support-gateway-new7"  # Name for the AgentCore Gateway
open_api_target_name = 'DemoOpenAPITargetS3NasaMars-new7'  # Name for the NASA API gateway target
lambda_target_name = "LambdaUsingSDK-new7"  # Name for the Lambda function gateway target

# S3 bucket configuration for storing OpenAPI specifications
unique_s3_name = str(uuid.uuid4())  # Generate a globally unique identifier for the bucket
bucket_name = f'agentcore-gateway-{unique_s3_name}'  # Prefix with 'agentcore-gateway' for clarity
file_path = 'openapi-specs/nasa_mars_insights_openapi.json'  # Local path to OpenAPI spec
object_key = 'nasa_mars_insights_openapi.json'  # S3 object key (filename in the bucket)

# Credential provider name for NASA API authentication
api_key_credential_provider_name = "NasaInsightAPIKey-new7"  # Will store the NASA API key securely

# Agent configuration
agent_name = "customer_support_gateway_new7"  # Name for the deployed agent in AgentCore Runtime


# Deploy the CloudFormation stack
lambda_arn, gateway_role_arn, runtime_execution_role_arn = deploy_stack(
    stack_name=stack_name,
    template_file=template_file,
    region=region,
    cf_client=cf_client
)
logger.info(f"stack created successfully for lmabda function, gateway role and runtime execution role")


# lambda_arn = 'arn:aws:lambda:us-east-1:233736836855:function:customer-support-lambda-stack-new4-customer-support'
# gateway_role_arn = 'arn:aws:iam::233736836855:role/customer-support-lambda-stack--GatewayAgentCoreRole-vsJTYaZOzIkb'
# runtime_execution_role_arn = 'arn:aws:iam::233736836855:role/customer-support-lambda-s-AgentCoreRuntimeExecution-Zq6np74LH89N'

logger.info(lambda_arn)

logger.info(gateway_role_arn)

logger.info(runtime_execution_role_arn)

#################################################################################

# Create an AgentCore Gateway with AWS IAM as the authorizer
# This is the key feature - using AWS_IAM instead of CUSTOM_JWT for authentication
create_response = agentcore_client.create_gateway(
    name=gateway_name,
    roleArn=gateway_role_arn,  
    protocolType="MCP", 
    authorizerType="AWS_IAM", 
    description="AgentCore Gateway with AWS Lambda target type using AWS IAM for ingress auth",
)
logger.info(f"Gateway created: {create_response}")

gateway_id = create_response["gatewayId"]
gateway_url = create_response["gatewayUrl"]

# gateway_id = 'customer-support-gateway-new4-psnrlwdobi'
# gateway_url = 'https://customer-support-gateway-new4-psnrlwdobi.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp'


logger.info(f"Gateway ID: {gateway_id}")
logger.info(f"Gateway URL: {gateway_url}")

# Wait for gateway to be ACTIVE before creating targets
import time
while True:
    gateway_status = agentcore_client.get_gateway(gatewayIdentifier=gateway_id)
    status = gateway_status['status']
    logger.info(f"Gateway status: {status}")
    if status == 'READY':
        break
    elif status == 'FAILED':
        raise Exception("Gateway creation failed")
    time.sleep(2)

#########################################################################
#################################################################################

# Configure the Lambda function as a gateway target
# This transforms Lambda function operations into MCP tools that AI agents can use
lambda_target_config = {
    "mcp": {
        "lambda": {
            "lambdaArn": lambda_arn, 
            
            "toolSchema": {
                "inlinePayload": [
                    {
                        # First tool: retrieve customer profile information
                        "name": "get_customer_profile",
                        "description": "Retrieve customer profile using customer ID, email, or phone number",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                # Customer can be looked up by ID, email, or phone
                                "customer_id": {"type": "string"},
                                "email": {"type": "string"},
                                "phone": {"type": "string"},
                            },
                            # At minimum, customer_id is required
                            "required": ["customer_id"],
                        },
                    },
                    {
                        # Second tool: check warranty status for products
                        "name": "check_warranty_status",
                        "description": "Check the warranty status of a product using its serial number and optionally verify via email",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                # Serial number uniquely identifies the product
                                "serial_number": {"type": "string"},
                                # Customer email can be used for verification
                                "customer_email": {"type": "string"},
                            },
                            # Serial number is mandatory
                            "required": ["serial_number"],
                        },
                    },
                ]
            },
        }
    }
}

# Configure how the gateway authenticates to the Lambda function
# Using the gateway's IAM role (gateway_role_arn) to invoke Lambda
credential_config = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]

# Create the gateway target - this makes the Lambda function available as MCP tools
response = agentcore_client.create_gateway_target(
    gatewayIdentifier=gateway_id,  
    name=lambda_target_name,  
    description="Lambda Target using SDK",
    targetConfiguration=lambda_target_config,  
    credentialProviderConfigurations=credential_config,  
)


#################################################################################
nasa_api_key = 'DHzXGyI5vLToaGDDE0bqjIpTDNjwGyixzZR09gjA'

if not nasa_api_key:
    logger.error("NASA API Key is required. Please run the cell above and enter your API key.")
    raise ValueError("NASA API Key is required")

# Create a credential provider in AgentCore Identity to securely store the API key
# This allows the gateway to authenticate to the NASA API without exposing the key
response_api_key = identity_client.create_api_key_credential_provider(
    name=api_key_credential_provider_name,  
    apiKey=nasa_api_key,
)

logger.info(f"Credential provider response: {response_api_key}")

credential_provider_arn = response_api_key['credentialProviderArn']

# credential_provider_arn = 'arn:aws:bedrock-agentcore:us-east-1:233736836855:token-vault/default/apikeycredentialprovider/NasaInsightAPIKey-1'
logger.info(f"Egress Credentials provider ARN: {credential_provider_arn}")

#################################################################################
# Create Amazon S3 Bucket to upload [NASA OpenAPI Spec](./openapi-specs/nasa_mars_insights_openapi.json)
try:
    # Create an S3 bucket to store the OpenAPI specification file
    if region == "us-east-1":
        # us-east-1 doesn't require LocationConstraint
        s3bucket = s3_client.create_bucket(
            Bucket=bucket_name
        )
    else:
        # All other regions need LocationConstraint to specify the region
        s3bucket = s3_client.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={
                'LocationConstraint': region
            }
        )
    
    # Upload the OpenAPI specification JSON file to S3
    # The gateway will read this file to understand the NASA API structure
    with open(file_path, 'rb') as file_data:
        response = s3_client.put_object(
            Bucket=bucket_name,  
            Key=object_key,  
            Body=file_data  
        )

    openapi_s3_uri = f's3://{bucket_name}/{object_key}'
    print(f'Uploaded object S3 URI: {openapi_s3_uri}')
except Exception as e:
    print(f'Error uploading file: {e}')

#################################################################################

### Step 4.3 Configure outbound auth and Create the gateway target

# Configure the NASA OpenAPI target
# This will transform NASA's Mars Insight API into MCP tools
nasa_openapi_s3_target_config = {
    "mcp": {
        "openApiSchema": {
            "s3": {
                "uri": openapi_s3_uri
            }
        }
    }
}

# Configure API key authentication for outbound requests to NASA
# The gateway will attach the API key to every request to the NASA API
api_key_credential_config = [
    {
        "credentialProviderType": "API_KEY",
        "credentialProvider": {
            "apiKeyCredentialProvider": {
                # NASA expects the API key as a query parameter named "api_key"
                "credentialParameterName": "api_key", 
                
                # ARN of the credential provider we created earlier
                "providerArn": credential_provider_arn,
                
                # NASA API expects the key in the query string (not in headers)
                "credentialLocation": "QUERY_PARAMETER",  # Options: "HEADER" or "QUERY_PARAMETER"
                
                # Note: credentialPrefix (like "Basic" or "Bearer") is used for header-based auth
                # "credentialPrefix": " "  # Uncomment if using header-based token auth
            }
        }
    }
]

# open_api_target_name = 'DemoOpenAPITargetS3NasaMars-2'
# Create the OpenAPI gateway target
# This makes all NASA API operations available as MCP tools
response = agentcore_client.create_gateway_target(
    gatewayIdentifier=gateway_id,  
    name=open_api_target_name,  
    description='OpenAPI Target with S3Uri using SDK',
    targetConfiguration=nasa_openapi_s3_target_config,  
    credentialProviderConfigurations=api_key_credential_config 
)


#################################################################################

# Initialize the AgentCore Runtime manager
# This object handles the deployment of our agent to AWS Lambda
        
try:
    # Try to get existing agent info
    # agentcore_client = boto3.client('bedrock-agentcore-control', region_name=region)
    
    # List agents to find existing one
    agents = agentcore_client.list_agent_runtimes()
    for agent in agents.get('items', []):
        if agent_name in agent.get('agentRuntimeId', ''):
            existing_agent_arn = agent.get('agentRuntimeArn')
            print(f"✅ Found existing agent: {existing_agent_arn}")
            break
except Exception as e:
    print(f"⚠️ Could not check existing agents: {e}")

# Create deployment_info.json before agent deployment
deployment_info = {
    "agent_name": agent_name,
    "lambda_arn": lambda_arn,
    "gateway_role_arn": gateway_role_arn,
    "runtime_execution_role_arn": runtime_execution_role_arn,
    "gateway_id": gateway_id,
    "gateway_url": gateway_url,
    "gateway_region": region,
    "nasa_api_key": nasa_api_key,
    "credential_provider_arn": credential_provider_arn,
    "agentcore_runtime_arn": ""
}

with open('deployment_info.json', 'w') as f:
    json.dump(deployment_info, f, indent=2)
