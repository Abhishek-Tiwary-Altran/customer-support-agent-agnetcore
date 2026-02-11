"""
Gateway Helper Functions for AgentCore Examples

This module provides utility functions for AgentCore Gateway management,
including gateway creation, target configuration, and credential setup.
"""

import boto3
import json
import logging
from typing import Dict, List, Optional, Any
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def create_agentcore_gateway(
    gateway_name: str,
    gateway_role_arn: str,
    region: str = "us-east-1",
    authorizer_type: str = "AWS_IAM",
    description: str = "AgentCore Gateway for MCP tools"
) -> Dict[str, str]:
    """
    Create an AgentCore Gateway - handles existing gateways gracefully.
    
    Args:
        gateway_name: Name for the gateway
        gateway_role_arn: IAM role ARN for gateway execution
        region: AWS region
        authorizer_type: Authorization type (AWS_IAM or CUSTOM_JWT)
        description: Gateway description
    
    Returns:
        Dictionary with gateway_id and gateway_url
    """
    agentcore_client = boto3.client('bedrock-agentcore-control', region_name=region)
    
    try:
        # Prepare gateway creation parameters
        create_params = {
            "name": gateway_name,
            "roleArn": gateway_role_arn,
            "protocolType": "MCP",
            "authorizerType": authorizer_type,
            "description": description
        }
        
        # Add authorizerConfiguration based on type
        if authorizer_type == "CUSTOM_JWT":
            # For JWT, configuration is required
            create_params["authorizerConfiguration"] = {
                "customJWTAuthorizer": {
                    "discoveryUrl": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_bN2UDlQvw/.well-known/openid-configuration",
                    "allowedAudience": ["20cnaahqss4gb2s4mmbholjkh8"],
                    "allowedClients": ["20cnaahqss4gb2s4mmbholjkh8"]
                }
            }
        else:
            # For AWS_IAM, empty configuration
            create_params["authorizerConfiguration"] = {}
        
        response = agentcore_client.create_gateway(**create_params)
        
        gateway_id = response["gatewayId"]
        gateway_url = response["gatewayUrl"]
        
        logger.info(f"✅ Created AgentCore Gateway: {gateway_id}")
        logger.info(f"   Gateway URL: {gateway_url}")
        
        # Wait for gateway to be ready
        logger.info("⏳ Waiting for gateway to be ready...")
        
        max_attempts = 30
        for attempt in range(max_attempts):
            try:
                gateway_status = agentcore_client.get_gateway(gatewayIdentifier=gateway_id)
                status = gateway_status['status']
                
                if status == 'AVAILABLE':
                    logger.info("✅ Gateway is ready")
                    break
                elif status in ['FAILED', 'DELETING', 'DELETED']:
                    raise Exception(f"Gateway creation failed with status: {status}")
                else:
                    logger.info(f"Gateway status: {status}, waiting...")
                    import time
                    time.sleep(10)
            except Exception as e:
                if attempt == max_attempts - 1:
                    raise Exception(f"Gateway did not become ready after {max_attempts} attempts: {e}")
                import time
                time.sleep(10)
        
        return {
            "gateway_id": gateway_id,
            "gateway_url": gateway_url
        }
        
    except Exception as e:
        # Handle name conflicts gracefully
        if "already exists" in str(e).lower() or "conflict" in str(e).lower():
            logger.warning(f"Gateway {gateway_name} already exists, attempting to find it...")
            try:
                gateways = agentcore_client.list_gateways()
                for gateway in gateways.get('items', []):
                    if gateway.get('name') == gateway_name:
                        gateway_id = gateway['gatewayId']
                        gateway_url = gateway['gatewayUrl']
                        logger.info(f"✅ Found existing gateway: {gateway_id}")
                        return {
                            "gateway_id": gateway_id,
                            "gateway_url": gateway_url
                        }
                raise Exception(f"Gateway {gateway_name} exists but could not be found in list")
            except Exception as list_error:
                logger.error(f"Could not find existing gateway: {list_error}")
                raise e
        else:
            logger.error(f"❌ Failed to create AgentCore Gateway: {e}")
            raise


def create_lambda_gateway_target(
    gateway_id: str,
    target_name: str,
    lambda_arn: str,
    tools_config: List[Dict[str, Any]],
    region: str = "us-east-1",
    description: str = "Lambda function gateway target"
) -> str:
    """
    Create a Lambda function gateway target - handles existing targets gracefully.
    
    Args:
        gateway_id: Gateway ID
        target_name: Name for the target
        lambda_arn: Lambda function ARN
        tools_config: List of tool configurations
        region: AWS region
        description: Target description
    
    Returns:
        Target ID
    """
    agentcore_client = boto3.client('bedrock-agentcore-control', region_name=region)
    
    # Configure Lambda target
    target_config = {
        "mcp": {
            "lambda": {
                "lambdaArn": lambda_arn,
                "toolSchema": {
                    "inlinePayload": tools_config
                }
            }
        }
    }
    
    # Use gateway IAM role for authentication
    credential_config = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
    
    try:
        response = agentcore_client.create_gateway_target(
            gatewayIdentifier=gateway_id,
            name=target_name,
            description=description,
            targetConfiguration=target_config,
            credentialProviderConfigurations=credential_config
        )
        
        logger.info(f"✅ Created Lambda gateway target: {target_name}")
        return response.get("targetId", target_name)
        
    except Exception as e:
        # Handle existing targets gracefully
        if "already exists" in str(e).lower() or "conflict" in str(e).lower():
            logger.warning(f"Target {target_name} already exists, attempting to find it...")
            try:
                targets = agentcore_client.list_gateway_targets(gatewayIdentifier=gateway_id)
                for target in targets.get('items', []):
                    if target.get('name') == target_name:
                        target_id = target.get('targetId') or target.get('id')
                        logger.info(f"✅ Found existing Lambda target: {target_name}")
                        return target_id
                raise Exception(f"Target {target_name} exists but could not be found in list")
            except Exception as list_error:
                logger.error(f"Could not find existing target: {list_error}")
                raise e
        else:
            logger.error(f"❌ Failed to create Lambda gateway target: {e}")
            raise


def create_openapi_gateway_target(
    gateway_id: str,
    target_name: str,
    openapi_s3_uri: str,
    credential_provider_arn: str,
    credential_parameter_name: str = "api_key",
    credential_location: str = "QUERY_PARAMETER",
    region: str = "us-east-1",
    description: str = "OpenAPI gateway target"
) -> str:
    """
    Create an OpenAPI gateway target.
    
    Args:
        gateway_id: Gateway ID
        target_name: Name for the target
        openapi_s3_uri: S3 URI of OpenAPI specification
        credential_provider_arn: ARN of credential provider
        credential_parameter_name: Name of credential parameter
        credential_location: Location of credential (QUERY_PARAMETER or HEADER)
        region: AWS region
        description: Target description
    
    Returns:
        Target ID
    """
    agentcore_client = boto3.client('bedrock-agentcore-control', region_name=region)
    
    # Configure OpenAPI target
    target_config = {
        "mcp": {
            "openApiSchema": {
                "s3": {
                    "uri": openapi_s3_uri
                }
            }
        }
    }
    
    # Configure API key authentication
    credential_config = [
        {
            "credentialProviderType": "API_KEY",
            "credentialProvider": {
                "apiKeyCredentialProvider": {
                    "credentialParameterName": credential_parameter_name,
                    "providerArn": credential_provider_arn,
                    "credentialLocation": credential_location
                }
            }
        }
    ]
    
    try:
        response = agentcore_client.create_gateway_target(
            gatewayIdentifier=gateway_id,
            name=target_name,
            description=description,
            targetConfiguration=target_config,
            credentialProviderConfigurations=credential_config
        )
        
        logger.info(f"✅ Created OpenAPI gateway target: {target_name}")
        return response.get("targetId", target_name)
        
    except Exception as e:
        logger.error(f"❌ Failed to create OpenAPI gateway target: {e}")
        raise


def create_api_key_credential_provider(
    provider_name: str,
    api_key: str,
    region: str = "us-east-1"
) -> str:
    """
    Create an API key credential provider - handles existing providers gracefully.
    
    Args:
        provider_name: Name for the credential provider
        api_key: API key value
        region: AWS region
    
    Returns:
        Credential provider ARN
    """
    identity_client = boto3.client('bedrock-agentcore-control', region_name=region)
    
    try:
        response = identity_client.create_api_key_credential_provider(
            name=provider_name,
            apiKey=api_key
        )
        
        credential_provider_arn = response['credentialProviderArn']
        logger.info(f"✅ Created API key credential provider: {credential_provider_arn}")
        
        return credential_provider_arn
        
    except Exception as e:
        # Handle existing credential providers gracefully
        if "already exists" in str(e).lower() or "conflict" in str(e).lower():
            logger.warning(f"Credential provider {provider_name} already exists")
            # Construct ARN manually since there's no list API
            try:
                sts_client = boto3.client('sts', region_name=region)
                account_id = sts_client.get_caller_identity()["Account"]
                credential_provider_arn = f"arn:aws:bedrock-agentcore:{region}:{account_id}:token-vault/default/apikeycredentialprovider/{provider_name}"
                logger.info(f"✅ Using existing credential provider: {credential_provider_arn}")
                return credential_provider_arn
            except Exception as arn_error:
                logger.error(f"Could not construct credential provider ARN: {arn_error}")
                raise e
        else:
            logger.error(f"❌ Failed to create API key credential provider: {e}")
            raise


def list_gateway_tools(
    gateway_url: str,
    region: str = "us-east-1",
    service_name: str = "bedrock-agentcore"
) -> List[Any]:
    """
    List all tools available from a gateway.
    
    Args:
        gateway_url: Gateway URL
        region: AWS region
        service_name: AWS service name for SigV4 signing
    
    Returns:
        List of tool objects
    """
    from strands.tools.mcp.mcp_client import MCPClient
    from streamable_http_sigv4 import streamablehttp_client_with_sigv4
    
    try:
        # Create MCP client with SigV4 authentication
        session = boto3.Session()
        credentials = session.get_credentials()
        
        mcp_client = MCPClient(
            lambda: streamablehttp_client_with_sigv4(
                url=gateway_url,
                credentials=credentials,
                service=service_name,
                region=region
            )
        )
        
        with mcp_client:
            # Get all tools with pagination
            tools = []
            pagination_token = None
            
            while True:
                tmp_tools = mcp_client.list_tools_sync(pagination_token=pagination_token)
                tools.extend(tmp_tools)
                
                if tmp_tools.pagination_token is None:
                    break
                else:
                    pagination_token = tmp_tools.pagination_token
            
            logger.info(f"✅ Found {len(tools)} tools in gateway")
            for tool in tools:
                logger.info(f"   - {tool.tool_name}")
            
            return tools
        
    except Exception as e:
        logger.error(f"❌ Failed to list gateway tools: {e}")
        return []


def delete_gateway_and_targets(
    gateway_id: str,
    region: str = "us-east-1"
) -> None:
    """
    Delete a gateway and all its targets.
    
    Args:
        gateway_id: Gateway ID to delete
        region: AWS region
    """
    agentcore_client = boto3.client('bedrock-agentcore-control', region_name=region)
    
    try:
        # List and delete all targets first
        targets_response = agentcore_client.list_gateway_targets(
            gatewayIdentifier=gateway_id
        )
        
        for target in targets_response.get('items', []):
            target_id = target['targetId']
            try:
                agentcore_client.delete_gateway_target(
                    gatewayIdentifier=gateway_id,
                    targetIdentifier=target_id
                )
                logger.info(f"✅ Deleted gateway target: {target_id}")
            except Exception as e:
                logger.error(f"❌ Failed to delete target {target_id}: {e}")
        
        # Delete the gateway
        agentcore_client.delete_gateway(gatewayIdentifier=gateway_id)
        logger.info(f"✅ Deleted gateway: {gateway_id}")
        
    except Exception as e:
        logger.error(f"❌ Failed to delete gateway: {e}")


def delete_credential_provider(
    provider_name: str,
    region: str = "us-east-1"
) -> None:
    """
    Delete an API key credential provider.
    
    Args:
        provider_name: Name of the credential provider
        region: AWS region
    """
    identity_client = boto3.client('bedrock-agentcore-control', region_name=region)
    
    try:
        identity_client.delete_api_key_credential_provider(name=provider_name)
        logger.info(f"✅ Deleted credential provider: {provider_name}")
        
    except Exception as e:
        logger.error(f"❌ Failed to delete credential provider: {e}")


# Pre-defined tool configurations for common use cases
LAMBDA_TOOL_CONFIGS = {
    "customer_support": [
        {
            "name": "get_customer_profile",
            "description": "Retrieve customer profile using customer ID, email, or phone number",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                    "email": {"type": "string"},
                    "phone": {"type": "string"}
                },
                "required": ["customer_id"]
            }
        },
        {
            "name": "check_warranty_status",
            "description": "Check the warranty status of a product using its serial number",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "serial_number": {"type": "string"},
                    "customer_email": {"type": "string"}
                },
                "required": ["serial_number"]
            }
        }
    ],
    "order_management": [
        {
            "name": "get_order_status",
            "description": "Get the status of an order by order ID",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "customer_id": {"type": "string"}
                },
                "required": ["order_id"]
            }
        },
        {
            "name": "update_order",
            "description": "Update order information",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "updates": {"type": "object"}
                },
                "required": ["order_id", "updates"]
            }
        }
    ],
    "inventory_management": [
        {
            "name": "check_inventory",
            "description": "Check product inventory levels",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "location": {"type": "string"}
                },
                "required": ["product_id"]
            }
        },
        {
            "name": "reserve_inventory",
            "description": "Reserve inventory for an order",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "quantity": {"type": "integer"},
                    "reservation_id": {"type": "string"}
                },
                "required": ["product_id", "quantity"]
            }
        }
    ]
}


def get_gateway_configuration_template(use_case: str) -> Dict[str, Any]:
    """
    Get a pre-configured gateway template for common use cases.
    
    Args:
        use_case: Use case name (customer_support, order_management, etc.)
    
    Returns:
        Gateway configuration template
    """
    templates = {
        "customer_support": {
            "gateway_name": "customer-support-gateway",
            "description": "Gateway for customer support operations",
            "targets": [
                {
                    "name": "CustomerSupportLambda",
                    "type": "lambda",
                    "tools": LAMBDA_TOOL_CONFIGS["customer_support"]
                }
            ]
        },
        "ecommerce": {
            "gateway_name": "ecommerce-gateway",
            "description": "Gateway for e-commerce operations",
            "targets": [
                {
                    "name": "OrderManagement",
                    "type": "lambda",
                    "tools": LAMBDA_TOOL_CONFIGS["order_management"]
                },
                {
                    "name": "InventoryManagement",
                    "type": "lambda",
                    "tools": LAMBDA_TOOL_CONFIGS["inventory_management"]
                }
            ]
        },
        "external_apis": {
            "gateway_name": "external-apis-gateway",
            "description": "Gateway for external API integrations",
            "targets": [
                {
                    "name": "NASAWeatherAPI",
                    "type": "openapi",
                    "openapi_spec": "nasa_mars_insights.json",
                    "credential_param": "api_key",
                    "credential_location": "QUERY_PARAMETER"
                }
            ]
        }
    }
    
    return templates.get(use_case, {})


def setup_complete_gateway(
    use_case: str,
    gateway_role_arn: str,
    lambda_arns: Dict[str, str] = None,
    api_credentials: Dict[str, str] = None,
    openapi_s3_uris: Dict[str, str] = None,
    region: str = "us-east-1"
) -> Dict[str, Any]:
    """
    Set up a complete gateway configuration for a specific use case.
    
    Args:
        use_case: Use case name
        gateway_role_arn: IAM role ARN for gateway
        lambda_arns: Dictionary mapping target names to Lambda ARNs
        api_credentials: Dictionary mapping API names to credentials
        openapi_s3_uris: Dictionary mapping API names to S3 URIs
        region: AWS region
    
    Returns:
        Dictionary with gateway information and target IDs
    """
    template = get_gateway_configuration_template(use_case)
    if not template:
        raise ValueError(f"Unknown use case: {use_case}")
    
    # Create the gateway
    gateway_info = create_agentcore_gateway(
        gateway_name=template["gateway_name"],
        gateway_role_arn=gateway_role_arn,
        region=region,
        description=template["description"]
    )
    
    gateway_id = gateway_info["gateway_id"]
    target_ids = {}
    
    # Create targets
    for target_config in template["targets"]:
        target_name = target_config["name"]
        
        if target_config["type"] == "lambda":
            if not lambda_arns or target_name not in lambda_arns:
                logger.warning(f"Lambda ARN not provided for target: {target_name}")
                continue
            
            target_id = create_lambda_gateway_target(
                gateway_id=gateway_id,
                target_name=target_name,
                lambda_arn=lambda_arns[target_name],
                tools_config=target_config["tools"],
                region=region
            )
            target_ids[target_name] = target_id
            
        elif target_config["type"] == "openapi":
            if not api_credentials or not openapi_s3_uris:
                logger.warning(f"API credentials or S3 URI not provided for target: {target_name}")
                continue
            
            # Create credential provider
            api_key = api_credentials.get(target_name)
            if api_key:
                credential_provider_arn = create_api_key_credential_provider(
                    provider_name=f"{target_name}CredentialProvider",
                    api_key=api_key,
                    region=region
                )
                
                target_id = create_openapi_gateway_target(
                    gateway_id=gateway_id,
                    target_name=target_name,
                    openapi_s3_uri=openapi_s3_uris[target_name],
                    credential_provider_arn=credential_provider_arn,
                    credential_parameter_name=target_config.get("credential_param", "api_key"),
                    credential_location=target_config.get("credential_location", "QUERY_PARAMETER"),
                    region=region
                )
                target_ids[target_name] = target_id
    
    return {
        "gateway_id": gateway_id,
        "gateway_url": gateway_info["gateway_url"],
        "target_ids": target_ids
    }