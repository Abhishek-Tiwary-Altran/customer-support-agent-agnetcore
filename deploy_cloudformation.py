import boto3
import time
import logging
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

def deploy_stack(stack_name, template_file, cf_client, region=None, parameters=None):
    """
    Deploy a CloudFormation stack
    
    Args:
        stack_name (str): Name of the CloudFormation stack
        template_file (str): Path to the CloudFormation template file
        cf_client: Boto3 CloudFormation client
        region (str): AWS region (optional, for compatibility)
        parameters (list): Optional list of parameters for the stack
    
    Returns:
        tuple: (lambda_arn, gateway_role_arn, runtime_execution_role_arn)
    """
    try:
        # Read the template file
        with open(template_file, 'r') as f:
            template_body = f.read()
        
        # Prepare stack parameters
        stack_params = {
            'StackName': stack_name,
            'TemplateBody': template_body,
            'Capabilities': ['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM']
        }
        
        if parameters:
            stack_params['Parameters'] = parameters
        
        # Check if stack exists
        try:
            cf_client.describe_stacks(StackName=stack_name)
            logger.info(f"Stack {stack_name} exists. Updating...")
            
            # Update existing stack
            response = cf_client.update_stack(**stack_params)
            operation = 'UPDATE'
            
        except ClientError as e:
            if 'does not exist' in str(e):
                logger.info(f"Stack {stack_name} does not exist. Creating...")
                
                # Create new stack
                response = cf_client.create_stack(**stack_params)
                operation = 'CREATE'
            else:
                raise e
        
        # Wait for stack operation to complete
        stack_id = response['StackId']
        logger.info(f"Stack {operation} initiated. Stack ID: {stack_id}")
        
        # Wait for completion
        if operation == 'CREATE':
            waiter = cf_client.get_waiter('stack_create_complete')
        else:
            waiter = cf_client.get_waiter('stack_update_complete')
        
        logger.info(f"Waiting for stack {operation} to complete...")
        waiter.wait(
            StackName=stack_name,
            WaiterConfig={
                'Delay': 30,
                'MaxAttempts': 120
            }
        )
        
        # Get final stack status
        stack_info = cf_client.describe_stacks(StackName=stack_name)
        stack_status = stack_info['Stacks'][0]['StackStatus']
        
        logger.info(f"Stack {operation} completed with status: {stack_status}")
        
        # Get stack outputs
        outputs = get_stack_outputs(stack_name, cf_client)
        
        # Extract the required ARNs from outputs
        lambda_arn = outputs.get('CustomerSupportLambdaArn', '')
        gateway_role_arn = outputs.get('GatewayAgentCoreRoleArn', '')
        runtime_execution_role_arn = outputs.get('AgentCoreRuntimeExecutionRoleArn', '')
        
        logger.info(f"Stack outputs - Lambda ARN: {lambda_arn}")
        logger.info(f"Stack outputs - Gateway Role ARN: {gateway_role_arn}")
        logger.info(f"Stack outputs - Runtime Role ARN: {runtime_execution_role_arn}")
        
        return lambda_arn, gateway_role_arn, runtime_execution_role_arn
        
    except ClientError as e:
        if 'No updates are to be performed' in str(e):
            logger.info(f"No updates needed for stack {stack_name}")
            # Get stack outputs even when no updates needed
            outputs = get_stack_outputs(stack_name, cf_client)
            lambda_arn = outputs.get('CustomerSupportLambdaArn', '')
            gateway_role_arn = outputs.get('GatewayAgentCoreRoleArn', '')
            runtime_execution_role_arn = outputs.get('AgentCoreRuntimeExecutionRoleArn', '')
            
            return lambda_arn, gateway_role_arn, runtime_execution_role_arn
        else:
            logger.error(f"Error deploying stack {stack_name}: {str(e)}")
            raise e
    except Exception as e:
        logger.error(f"Unexpected error deploying stack {stack_name}: {str(e)}")
        raise e

def delete_stack(stack_name, cf_client):
    """
    Delete a CloudFormation stack
    
    Args:
        stack_name (str): Name of the CloudFormation stack to delete
        cf_client: Boto3 CloudFormation client
    
    Returns:
        dict: Stack deletion result
    """
    try:
        # Check if stack exists
        try:
            cf_client.describe_stacks(StackName=stack_name)
        except ClientError as e:
            if 'does not exist' in str(e):
                logger.info(f"Stack {stack_name} does not exist. Nothing to delete.")
                return {
                    'StackName': stack_name,
                    'Status': 'STACK_NOT_FOUND',
                    'Operation': 'DELETE'
                }
            else:
                raise e
        
        # Delete the stack
        logger.info(f"Deleting stack {stack_name}...")
        cf_client.delete_stack(StackName=stack_name)
        
        # Wait for deletion to complete
        waiter = cf_client.get_waiter('stack_delete_complete')
        logger.info(f"Waiting for stack {stack_name} deletion to complete...")
        
        waiter.wait(
            StackName=stack_name,
            WaiterConfig={
                'Delay': 30,
                'MaxAttempts': 120
            }
        )
        
        logger.info(f"Stack {stack_name} deleted successfully")
        
        return {
            'StackName': stack_name,
            'Status': 'DELETE_COMPLETE',
            'Operation': 'DELETE'
        }
        
    except ClientError as e:
        logger.error(f"Error deleting stack {stack_name}: {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected error deleting stack {stack_name}: {str(e)}")
        raise e

def get_stack_outputs(stack_name, cf_client):
    """
    Get outputs from a CloudFormation stack
    
    Args:
        stack_name (str): Name of the CloudFormation stack
        cf_client: Boto3 CloudFormation client
    
    Returns:
        dict: Stack outputs as key-value pairs
    """
    try:
        response = cf_client.describe_stacks(StackName=stack_name)
        stack = response['Stacks'][0]
        
        outputs = {}
        if 'Outputs' in stack:
            for output in stack['Outputs']:
                outputs[output['OutputKey']] = output['OutputValue']
        
        return outputs
        
    except ClientError as e:
        logger.error(f"Error getting stack outputs for {stack_name}: {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected error getting stack outputs for {stack_name}: {str(e)}")
        raise e