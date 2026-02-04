import subprocess
def get_egress_ip():
	try:
		result = subprocess.run(['curl', '-s', 'ifconfig.me'], capture_output=True, text=True, check=True)
		egress_ip = result.stdout.strip()
		print(f"Egress IP: {egress_ip}")
		return egress_ip
	except Exception as e:
		print(f"Failed to get egress IP: {e}")
		return None

import os
from dotenv import load_dotenv
import requests
import base64

base_url = "https://api.lumen.com"

import time

def get_access_token() -> str:
	"""
	Request a new access token and store it in .env along with its expiry time.
	Returns the access token string on success, otherwise None.
	"""
	load_dotenv()
	url = f"{base_url}/oauth/v2/token"
	payload = 'grant_type=client_credentials'
	username = os.getenv('USERNAME')
	secret = os.getenv('SECRET')
	if not username or not secret:
		raise ValueError("USERNAME and SECRET must be set in .env file.")
	basic_auth = base64.b64encode(f"{username}:{secret}".encode()).decode()
	headers = {
		'Content-Type': 'application/x-www-form-urlencoded',
		'Authorization': f"Basic {basic_auth}"
	}
	response = requests.post(url, headers=headers, data=payload)
	if response.status_code == 200:
		data = response.json()
		access_token = data.get('access_token')
		expires_in = data.get('expires_in')
		now = int(time.time())
		if access_token:
			# Overwrite ACCESS_TOKEN and ACCESS_TOKEN_EXPIRES_AT in .env file
			env_path = '.env'
			lines = []
			with open(env_path, 'r') as env_file:
				lines = env_file.readlines()
			with open(env_path, 'w') as env_file:
				found_token = False
				found_exp = False
				for line in lines:
					if line.startswith('ACCESS_TOKEN='):
						env_file.write(f"ACCESS_TOKEN={access_token}\n")
						found_token = True
					elif line.startswith('ACCESS_TOKEN_EXPIRES_AT='):
						# write computed expiry if available
						if expires_in:
							expires_at = now + int(expires_in)
							env_file.write(f"ACCESS_TOKEN_EXPIRES_AT={expires_at}\n")
						else:
							env_file.write(line)
						found_exp = True
					else:
						env_file.write(line)
				if not found_token:
					env_file.write(f"ACCESS_TOKEN={access_token}\n")
				if not found_exp and expires_in:
					expires_at = now + int(expires_in)
					env_file.write(f"ACCESS_TOKEN_EXPIRES_AT={expires_at}\n")
			print(f"ACCESS_TOKEN value '{access_token}' updated in .env (expires_in={expires_in})")
			return access_token
		else:
			print("No access token found in response.")
	else:
		print(f"Failed to get token: {response.status_code} {response.text}")
	return None


def is_access_token_expired(buffer_seconds: int = 60) -> bool:
	"""Return True if the stored access token is missing or will expire within buffer_seconds."""
	load_dotenv()
	expires_at = os.getenv('ACCESS_TOKEN_EXPIRES_AT')
	if not expires_at:
		return True
	try:
		expires_at_i = int(expires_at)
		return expires_at_i <= int(time.time()) + int(buffer_seconds)
	except Exception:
		# if parsing fails, treat as expired
		return True


def get_valid_access_token(buffer_seconds: int = 60) -> str:
	"""Return a valid access token, refreshing it if missing/expired."""
	load_dotenv()
	token = os.getenv('ACCESS_TOKEN')
	if token and not is_access_token_expired(buffer_seconds):
		return token
	# refresh
	new = get_access_token()
	if not new:
		raise ValueError("Failed to obtain access token")
	return new




def get_quote():
    access_token = get_valid_access_token()
    url = f"{base_url}/v2/quotes"
    headers = {
        'Authorization': f"Bearer {access_token}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        print("Quotes retrieved successfully.")
        return data
    else:
        print(f"Failed to get quotes: {response.status_code} {response.text}")
        return None




def check_inventory(service_id: str = None, page_number: int = 1, page_size: int = 10, naas_enabled: bool = True, entitled: bool = True, service_type: str = "Internet", access_token: str = None):
    """
    Check Lumen product inventory for a given service.

    Values pulled from .env when not provided:
    - CUSTOMER_NUMBER -> header 'x-customer-number'
    - SERVICE_ID -> used as serviceId query param when service_id not provided
    - ACCESS_TOKEN -> Bearer token (will attempt to refresh via get_access_token()
      if missing)

    Returns parsed JSON on success or raw text on non-JSON responses.
    """
    load_dotenv()

    customer_number = os.getenv('CUSTOMER_NUMBER')
    env_service_id = os.getenv('SERVICE_ID')
    access_token = access_token or get_valid_access_token()

    if not customer_number:
        raise ValueError("CUSTOMER_NUMBER must be set in .env file.")

    service_id = service_id or env_service_id
    if not service_id:
        raise ValueError("service_id parameter or SERVICE_ID in .env must be provided.")

    headers = {
        'x-customer-number': customer_number,
        'Authorization': f'Bearer {access_token}'
    }

    params = {
        'pageNumber': page_number,
        'pageSize': page_size,
        'naasEnabled': str(naas_enabled).lower(),
        'entitled': str(entitled).lower(),
        'serviceType': service_type,
        'serviceId': service_id
    }

    url = f"{base_url}/ProductInventory/v1/inventory"

    resp = requests.get(url, headers=headers, params=params)
    print(resp.text)
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        print(f"Inventory request failed: {resp.status_code} {resp.text}")
        raise

    try:
        return resp.json()
    except ValueError:
        return resp.text


if __name__ == "__main__":
	get_access_token()
	egress_ip = get_egress_ip()

