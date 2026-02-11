"""
AWS Helper Functions for AgentCore Examples

This module provides utility functions for AWS service interactions,
IAM role management, and resource setup.
"""

import boto3
import json
import time
import logging
from typing import Dict, Optional, List
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def get_aws_session(region: str = "us-east-1") -> boto3.Session:
    """Get configured AWS session."""
    return boto3.Session(region_name=region)


def get_account_id() -> str:
    """Get current AWS account ID."""
    sts_client = boto3.client('sts')
    return sts_client.get_caller_identity()['Account']


def create_agentcore_execution_role(
    role_name: str,
    region: str = "us-east-1",
    account_id: Optional[str] = None
) -> str:
    """
    Create IAM execution role for AgentCore Runtime.
    
    Args:
        role_name: Name for the IAM role
        region: AWS region
        account_id: AWS account ID (auto-detected if not provided)
    
    Returns:
        Role ARN
    """
    if not account_id:
        account_id = get_account_id()
    
    iam_client = boto3.client('iam', region_name=region)
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
    
    # Trust policy for AgentCore Runtime
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AssumeRolePolicy",
                "Effect": "Allow",
                "Principal": {
                    "Service": "bedrock-agentcore.amazonaws.com"
                },
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {
                        "aws:SourceAccount": account_id
                    },
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{region}:{account_id}:*"
                    }
                }
            }
        ]
    }
    
    # Permissions policy
    permissions_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "BedrockPermissions",
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream"
                ],
                "Resource": "*"
            },
            {
                "Sid": "ECRImageAccess",
                "Effect": "Allow",
                "Action": [
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:GetAuthorizationToken"
                ],
                "Resource": [
                    f"arn:aws:ecr:{region}:{account_id}:repository/*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:DescribeLogStreams",
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                "Resource": [
                    f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "xray:GetSamplingRules",
                    "xray:GetSamplingTargets"
                ],
                "Resource": ["*"]
            },
            {
                "Effect": "Allow",
                "Resource": "*",
                "Action": "cloudwatch:PutMetricData",
                "Condition": {
                    "StringEquals": {
                        "cloudwatch:namespace": "bedrock-agentcore"
                    }
                }
            },
            {
                "Sid": "GetAgentAccessToken",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:GetWorkloadAccessToken",
                    "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                    "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
                ],
                "Resource": [
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default",
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default/workload-identity/*"
                ]
            },
            {
                "Sid": "InvokeGateway",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:InvokeGateway"
                ],
                "Resource": ["*"]
            }
        ]
    }
    
    try:
        # Check if role already exists
        try:
            existing_role = iam_client.get_role(RoleName=role_name)
            logger.info(f"✅ IAM role already exists: {role_arn}")
            return role_arn
        except ClientError as e:
            if e.response['Error']['Code'] != 'NoSuchEntity':
                raise
        
        # Create the role
        logger.info(f"Creating IAM role: {role_name}")
        iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Execution role for AgentCore Runtime",
            Tags=[
                {'Key': 'Purpose', 'Value': 'AgentCoreRuntime'},
                {'Key': 'Example', 'Value': 'AgentCoreComplete'}
            ]
        )
        
        # Attach the permissions policy
        policy_name = "AgentCoreRuntimePolicy"
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(permissions_policy)
        )
        
        # Wait for role to be available
        time.sleep(10)
        
        logger.info(f"✅ Successfully created IAM role: {role_arn}")
        return role_arn
        
    except ClientError as e:
        logger.error(f"❌ Failed to create IAM role: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error creating IAM role: {e}")
        raise


def create_gateway_execution_role(
    role_name: str,
    region: str = "us-east-1",
    account_id: Optional[str] = None
) -> str:
    """
    Create IAM execution role for AgentCore Gateway.
    
    Args:
        role_name: Name for the IAM role
        region: AWS region
        account_id: AWS account ID (auto-detected if not provided)
    
    Returns:
        Role ARN
    """
    if not account_id:
        account_id = get_account_id()
    
    iam_client = boto3.client('iam', region_name=region)
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
    
    # Trust policy for AgentCore Gateway
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "GatewayAssumeRolePolicy",
                "Effect": "Allow",
                "Principal": {
                    "Service": ["bedrock-agentcore.amazonaws.com"]
                },
                "Action": ["sts:AssumeRole"],
                "Condition": {
                    "StringEquals": {
                        "aws:SourceAccount": account_id
                    },
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{region}:{account_id}:gateway/*"
                    }
                }
            }
        ]
    }
    
    # Permissions policy
    permissions_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "BedrockAgentCorePolicy",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:*",
                    "bedrock:*",
                    "agent-credential-provider:*",
                    "iam:PassRole",
                    "secretsmanager:GetSecretValue",
                    "lambda:InvokeFunction",
                    "s3:*"
                ],
                "Resource": "*"
            }
        ]
    }
    
    try:
        # Check if role already exists
        try:
            existing_role = iam_client.get_role(RoleName=role_name)
            logger.info(f"✅ Gateway IAM role already exists: {role_arn}")
            return role_arn
        except ClientError as e:
            if e.response['Error']['Code'] != 'NoSuchEntity':
                raise
        
        # Create the role
        logger.info(f"Creating Gateway IAM role: {role_name}")
        iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Execution role for AgentCore Gateway",
            Tags=[
                {'Key': 'Purpose', 'Value': 'AgentCoreGateway'},
                {'Key': 'Example', 'Value': 'AgentCoreComplete'}
            ]
        )
        
        # Attach the permissions policy
        policy_name = "AgentCoreGatewayPolicy"
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(permissions_policy)
        )
        
        # Wait for role to be available
        time.sleep(10)
        
        logger.info(f"✅ Successfully created Gateway IAM role: {role_arn}")
        return role_arn
        
    except ClientError as e:
        logger.error(f"❌ Failed to create Gateway IAM role: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error creating Gateway IAM role: {e}")
        raise


def create_memory_execution_role(
    role_name: str,
    region: str = "us-east-1",
    account_id: Optional[str] = None
) -> str:
    """
    Create IAM execution role for AgentCore Memory custom strategies.
    
    Args:
        role_name: Name for the IAM role
        region: AWS region
        account_id: AWS account ID (auto-detected if not provided)
    
    Returns:
        Role ARN
    """
    if not account_id:
        account_id = get_account_id()
    
    iam_client = boto3.client('iam', region_name=region)
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
    
    # Trust policy for AgentCore Memory
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "",
                "Effect": "Allow",
                "Principal": {
                    "Service": ["bedrock-agentcore.amazonaws.com"]
                },
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {
                        "aws:SourceAccount": account_id
                    },
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{region}:{account_id}:*"
                    }
                }
            }
        ]
    }
    
    # Permissions policy for Bedrock model invocation
    permissions_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream"
                ],
                "Resource": [
                    "arn:aws:bedrock:*::foundation-model/*",
                    f"arn:aws:bedrock:*:{account_id}:inference-profile/*"
                ],
                "Condition": {
                    "StringEquals": {
                        "aws:ResourceAccount": account_id
                    }
                }
            }
        ]
    }
    
    try:
        # Check if role already exists
        try:
            existing_role = iam_client.get_role(RoleName=role_name)
            logger.info(f"✅ Memory IAM role already exists: {role_arn}")
            return role_arn
        except ClientError as e:
            if e.response['Error']['Code'] != 'NoSuchEntity':
                raise
        
        # Create the role
        logger.info(f"Creating Memory IAM role: {role_name}")
        iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Execution role for AgentCore Memory custom strategies",
            Tags=[
                {'Key': 'Purpose', 'Value': 'AgentCoreMemory'},
                {'Key': 'Example', 'Value': 'AgentCoreComplete'}
            ]
        )
        
        # Attach the permissions policy
        policy_name = "AgentCoreMemoryBedrockAccess"
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(permissions_policy)
        )
        
        # Wait for role to be available
        time.sleep(10)
        
        logger.info(f"✅ Successfully created Memory IAM role: {role_arn}")
        return role_arn
        
    except ClientError as e:
        logger.error(f"❌ Failed to create Memory IAM role: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error creating Memory IAM role: {e}")
        raise


def setup_s3_bucket(bucket_name: str, region: str = "us-east-1") -> str:
    """
    Create S3 bucket for storing OpenAPI specifications and other resources.
    
    Args:
        bucket_name: Name for the S3 bucket
        region: AWS region
    
    Returns:
        Bucket name
    """
    s3_client = boto3.client('s3', region_name=region)
    
    try:
        # Check if bucket already exists
        try:
            s3_client.head_bucket(Bucket=bucket_name)
            logger.info(f"✅ S3 bucket already exists: {bucket_name}")
            return bucket_name
        except ClientError as e:
            if e.response['Error']['Code'] != '404':
                raise
        
        # Create the bucket
        logger.info(f"Creating S3 bucket: {bucket_name}")
        if region == "us-east-1":
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={'LocationConstraint': region}
            )
        
        # Enable versioning
        s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        
        logger.info(f"✅ Successfully created S3 bucket: {bucket_name}")
        return bucket_name
        
    except ClientError as e:
        logger.error(f"❌ Failed to create S3 bucket: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error creating S3 bucket: {e}")
        raise


def upload_file_to_s3(
    bucket_name: str,
    file_path: str,
    object_key: str,
    region: str = "us-east-1"
) -> str:
    """
    Upload file to S3 bucket.
    
    Args:
        bucket_name: S3 bucket name
        file_path: Local file path
        object_key: S3 object key
        region: AWS region
    
    Returns:
        S3 URI
    """
    s3_client = boto3.client('s3', region_name=region)
    
    try:
        with open(file_path, 'rb') as file_data:
            s3_client.put_object(
                Bucket=bucket_name,
                Key=object_key,
                Body=file_data
            )
        
        s3_uri = f"s3://{bucket_name}/{object_key}"
        logger.info(f"✅ Uploaded file to S3: {s3_uri}")
        return s3_uri
        
    except Exception as e:
        logger.error(f"❌ Failed to upload file to S3: {e}")
        raise


def cleanup_resources(
    role_names: List[str],
    bucket_names: List[str],
    region: str = "us-east-1"
) -> None:
    """
    Clean up AWS resources created by the example.
    
    Args:
        role_names: List of IAM role names to delete
        bucket_names: List of S3 bucket names to delete
        region: AWS region
    """
    iam_client = boto3.client('iam', region_name=region)
    s3_client = boto3.client('s3', region_name=region)
    
    # Delete IAM roles
    for role_name in role_names:
        try:
            # Delete attached policies first
            policies = iam_client.list_role_policies(RoleName=role_name)
            for policy_name in policies['PolicyNames']:
                iam_client.delete_role_policy(
                    RoleName=role_name,
                    PolicyName=policy_name
                )
            
            # Delete the role
            iam_client.delete_role(RoleName=role_name)
            logger.info(f"✅ Deleted IAM role: {role_name}")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchEntity':
                logger.info(f"IAM role does not exist: {role_name}")
            else:
                logger.error(f"❌ Failed to delete IAM role {role_name}: {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error deleting IAM role {role_name}: {e}")
    
    # Delete S3 buckets
    for bucket_name in bucket_names:
        try:
            # Delete all objects first
            objects = s3_client.list_objects_v2(Bucket=bucket_name)
            if 'Contents' in objects:
                for obj in objects['Contents']:
                    s3_client.delete_object(Bucket=bucket_name, Key=obj['Key'])
            
            # Delete the bucket
            s3_client.delete_bucket(Bucket=bucket_name)
            logger.info(f"✅ Deleted S3 bucket: {bucket_name}")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchBucket':
                logger.info(f"S3 bucket does not exist: {bucket_name}")
            else:
                logger.error(f"❌ Failed to delete S3 bucket {bucket_name}: {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error deleting S3 bucket {bucket_name}: {e}")