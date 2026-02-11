#!/usr/bin/env python3
"""
Script to set up AWS Cognito User Pool for Streamlit authentication
"""

import boto3
import json
import os

def create_cognito_user_pool():
    """Create Cognito User Pool and App Client"""
    cognito_client = boto3.client('cognito-idp', region_name='us-east-1')
    
    try:
        # Create User Pool
        user_pool_response = cognito_client.create_user_pool(
            PoolName='customer-support-agent-pool',
            Policies={
                'PasswordPolicy': {
                    'MinimumLength': 8,
                    'RequireUppercase': True,
                    'RequireLowercase': True,
                    'RequireNumbers': True,
                    'RequireSymbols': False
                }
            },
            UsernameAttributes=['email'],
            AutoVerifiedAttributes=['email'],
            VerificationMessageTemplate={
                'DefaultEmailOption': 'CONFIRM_WITH_CODE'
            }
        )
        
        user_pool_id = user_pool_response['UserPool']['Id']
        print(f"✅ Created User Pool: {user_pool_id}")
        
        # Create App Client
        app_client_response = cognito_client.create_user_pool_client(
            UserPoolId=user_pool_id,
            ClientName='customer-support-agent-client',
            GenerateSecret=True,
            ExplicitAuthFlows=['USER_PASSWORD_AUTH'],
            SupportedIdentityProviders=['COGNITO']
        )
        
        client_id = app_client_response['UserPoolClient']['ClientId']
        client_secret = app_client_response['UserPoolClient']['ClientSecret']
        
        print(f"✅ Created App Client: {client_id}")
        
        # Save configuration
        config = {
            'COGNITO_USER_POOL_ID': user_pool_id,
            'COGNITO_CLIENT_ID': client_id,
            'COGNITO_CLIENT_SECRET': client_secret,
            'COGNITO_REGION': 'us-east-1'
        }
        
        with open('cognito_config.json', 'w') as f:
            json.dump(config, f, indent=2)
        
        print("\n📝 Configuration saved to cognito_config.json")
        print("\n🔧 Set these environment variables:")
        for key, value in config.items():
            print(f"export {key}={value}")
        
        return user_pool_id, client_id, client_secret
        
    except Exception as e:
        print(f"❌ Error creating Cognito resources: {e}")
        return None, None, None

def create_test_user(user_pool_id, email="test@example.com", password="TempPass123!"):
    """Create a test user in the User Pool"""
    cognito_client = boto3.client('cognito-idp', region_name='us-east-1')
    
    try:
        # Create user (using email as username)
        cognito_client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            UserAttributes=[
                {'Name': 'email', 'Value': email},
                {'Name': 'email_verified', 'Value': 'true'}
            ],
            TemporaryPassword=password,
            MessageAction='SUPPRESS'
        )
        
        # Set permanent password
        cognito_client.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=email,
            Password=password,
            Permanent=True
        )
        
        print(f"✅ Created test user: {email}")
        print(f"   Password: {password}")
        
    except Exception as e:
        print(f"❌ Error creating test user: {e}")

if __name__ == "__main__":
    print("🚀 Setting up AWS Cognito for Customer Support Agent...")
    
    user_pool_id, client_id, client_secret = create_cognito_user_pool()
    
    if user_pool_id:
        create_test_user(user_pool_id)
        print("\n✅ Setup complete! You can now run the Streamlit app with authentication.")
    else:
        print("\n❌ Setup failed. Please check your AWS credentials and permissions.")