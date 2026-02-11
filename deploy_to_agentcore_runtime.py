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

agentcore_runtime = Runtime()

existing_agent_arn = None


with open('deployment_info.json', 'r') as f:
    deployment_info = json.load(f)
gateway_url = deployment_info['gateway_url']
GATEWAY_REGION = deployment_info.get('gateway_region', 'us-east-1')
runtime_execution_role_arn = deployment_info['runtime_execution_role_arn']

# Agent configuration
agent_name = deployment_info["agent_name"]

# Configure the runtime deployment settings
# This prepares all necessary AWS resources for deploying the agent
response = agentcore_runtime.configure(
    entrypoint="strands_agent_with_gateway.py",  
    auto_create_ecr=True, 
    requirements_file="requirements.txt",  
    region=region,  
    agent_name=agent_name,
    execution_role=runtime_execution_role_arn
)

# Display the configuration response
logger.info(f"the agentcore runtime response is {response}")

# Launch the agent to AWS Lambda via AgentCore Runtime
# This builds the container image, pushes it to ECR, and creates the Lambda function
# Note: This step can take several minutes as it builds and uploads the container
launch_result = agentcore_runtime.launch(env_vars={
    "GATEWAY_URL": gateway_url,
    "GATEWAY_REGION": region,
})

# Display the configuration response
logger.info(f"the agentcore runtime launch result is {launch_result}")

agent_arn = launch_result.agent_arn if hasattr(launch_result, 'agent_arn') else existing_agent_arn
            
if existing_agent_arn and agent_arn != existing_agent_arn:
    print(f"✅ Agent updated: {agent_arn}")
elif existing_agent_arn:
    print(f"✅ Agent redeployed: {agent_arn}")
else:
    print(f"✅ Agent deployed: {agent_arn}")

print(f"Using execution role: {runtime_execution_role_arn}")

# Update deployment_info.json with agent runtime ARN
deployment_info["agentcore_runtime_arn"] = agent_arn

with open('deployment_info.json', 'w') as f:
    json.dump(deployment_info, f, indent=2)

logger.info("Deployment info updated with agent runtime ARN")