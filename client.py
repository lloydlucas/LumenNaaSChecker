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

def _update_env_file(updates: dict) -> None:
	"""Update or append keys in the local .env file.

	This is intentionally simple: it preserves the existing file layout and comments,
	replacing any lines that start with a key that's present in `updates`, and appending
	any keys not already present.
	"""
	env_path = '.env'
	lines = []
	if os.path.exists(env_path):
		with open(env_path, 'r') as f:
			lines = f.readlines()

	out_lines = []
	replaced = set()
	for line in lines:
		stripped = line.strip()
		if not stripped or stripped.startswith('#') or '=' not in line:
			out_lines.append(line)
			continue
		key = line.split('=', 1)[0]
		if key in updates:
			out_lines.append(f"{key}={updates[key]}\n")
			replaced.add(key)
		else:
			out_lines.append(line)

	for k, v in updates.items():
		if k not in replaced:
			out_lines.append(f"{k}={v}\n")

	with open(env_path, 'w') as f:
		f.writelines(out_lines)


def get_access_token(force: bool = False) -> str:
	"""
	Return a valid access token.

	If `force` is False the cached token is returned when present and not expired. When a new
	token is requested it is written to `.env` along with `ACCESS_TOKEN_EXPIRES_AT` (epoch secs)
	and the local environment variables are updated.
	
	Raises ValueError on failure to obtain a token.
	"""
	load_dotenv()
	if not force:
		token = os.getenv('ACCESS_TOKEN')
		if token and not is_access_token_expired():
			return token

	username = os.getenv('USERNAME')
	secret = os.getenv('SECRET')
	if not username or not secret:
		raise ValueError("USERNAME and SECRET must be set in .env file.")

	url = f"{base_url}/oauth/v2/token"
	payload = 'grant_type=client_credentials'
	basic_auth = base64.b64encode(f"{username}:{secret}".encode()).decode()
	headers = {
		'Content-Type': 'application/x-www-form-urlencoded',
		'Authorization': f"Basic {basic_auth}"
	}

	response = requests.post(url, headers=headers, data=payload)
	if response.status_code != 200:
		raise ValueError(f"Failed to get token: {response.status_code} {response.text}")

	data = response.json()
	access_token = data.get('access_token')
	expires_in = data.get('expires_in')
	if not access_token:
		raise ValueError("No access token found in response.")

	updates = {'ACCESS_TOKEN': access_token}
	if expires_in is not None:
		try:
			expires_at = int(time.time()) + int(expires_in)
			updates['ACCESS_TOKEN_EXPIRES_AT'] = str(expires_at)
		except Exception:
			# ignore expiry if parsing fails
			pass

	# write and update in-memory env for immediate use
	_update_env_file(updates)
	os.environ['ACCESS_TOKEN'] = access_token
	if 'ACCESS_TOKEN_EXPIRES_AT' in updates:
		os.environ['ACCESS_TOKEN_EXPIRES_AT'] = updates['ACCESS_TOKEN_EXPIRES_AT']

	print(f"ACCESS_TOKEN updated (expires_in={expires_in})")
	return access_token


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
	check_inventory()
    print("Done.")