import subprocess
import os
import requests
import base64
import time
import json
from dotenv import load_dotenv

base_url = "https://api.lumen.com"

def get_egress_ip():
	"""
	Retrieve the current egress IP address and persist it to .env as EGRESS_IP.
	
	Returns the IP address string, or None on failure.
	"""
	try:
		result = subprocess.run(['curl', '-s', 'ifconfig.me'], capture_output=True, text=True)
		egress_ip = result.stdout.strip()
		if not egress_ip:
			raise ValueError("No IP returned from ifconfig.me")
		
		print(f"{egress_ip}")
		_update_env_file({'EGRESS_IP': egress_ip})
		os.environ['EGRESS_IP'] = egress_ip
		return egress_ip
	except Exception as e:
		print(f"Failed to get egress IP: {e}")
		return None

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


def check_inventory():
	"""
	Query Lumen inventory API using service_id and customer_number from .env.
	Use ACCESS_TOKEN from env. Save billing account id/name and bandwidth to .env.
	Return the parsed JSON response.
	"""
	load_dotenv()
	service_id = os.getenv('SERVICE_ID')
	customer_number = os.getenv('CUSTOMER_NUMBER')
	access_token = os.getenv('ACCESS_TOKEN')
	if not service_id:
		raise ValueError('SERVICE_ID must be set in .env')
	if not customer_number:
		raise ValueError('CUSTOMER_NUMBER must be set in .env')
	if not access_token:
		raise ValueError('ACCESS_TOKEN must be set in .env')

	url = f"{base_url}/ProductInventory/v1/inventory?pageNumber=1&pageSize=10&naasEnabled=true&entitled=true&serviceType=Internet&serviceId={service_id}"
	headers = {
		'x-customer-number': customer_number,
		'Authorization': f'Bearer {access_token}'
	}

	response = requests.get(url, headers=headers)
	try:
		response.raise_for_status()
	except requests.HTTPError:
		print(f"Inventory request failed: {response.status_code} {response.text}")
		raise

	try:
		data = response.json()
	except ValueError:
		print(response.text)
		return response.text

	# Save billing account and bandwidth to env
	service_inventory = data.get('serviceInventory', []) if isinstance(data, dict) else []
	if service_inventory:
		svc = service_inventory[0]
		env_updates = {}
		billing = svc.get('billingAccount', {})
		if billing.get('id'):
			env_updates['BILLING_ACCOUNT_ID'] = billing['id']
		if billing.get('name'):
			env_updates['BILLING_ACCOUNT_NAME'] = billing['name']
		location = svc.get('location', {})
		if location.get('masterSiteid'):	
			env_updates['MASTER_SITE_ID'] = location['masterSiteid']
		bandwidth = next((pc.get('value') for pc in svc.get('productCharacteristic', []) or [] if pc.get('name') == 'Bandwidth'), None)
		if bandwidth:
			env_updates['SERVICE_BANDWIDTH'] = str(bandwidth).lower()
		if env_updates:
			_update_env_file(env_updates)
			for k, v in env_updates.items():
				os.environ[k] = v
	return data


def set_quote_bandwidth():
	"""
	Determine quote bandwidth based on egress IP comparison.
	
	Reads EGRESS_IP from .env and compares with LUMEN_IP:
	- If same: set QUOTE_BANDWIDTH = BANDWIDTH_FULL
	- If different: set QUOTE_BANDWIDTH = BANDWIDTH_HEARTBEAT
	
	Returns the bandwidth value set.
	"""
	load_dotenv()

	# Ensure we have an egress IP; if not, attempt to retrieve it
	egress_ip = os.getenv('EGRESS_IP')
	if not egress_ip:
		egress_ip = get_egress_ip()

	lumen_ip = os.getenv('LUMEN_IP')

	if not egress_ip:
		raise ValueError("EGRESS_IP must be set in .env file or retrievable via get_egress_ip().")
	if not lumen_ip:
		raise ValueError("LUMEN_IP must be set in .env file.")

	# Normalize values for comparison
	egress_ip_n = egress_ip.strip()
	lumen_ip_n = lumen_ip.strip()

	if egress_ip_n == lumen_ip_n:
		bandwidth = os.getenv('BANDWIDTH_FULL')
		source = 'BANDWIDTH_FULL'
	else:
		bandwidth = os.getenv('BANDWIDTH_HEARTBEAT')
		source = 'BANDWIDTH_HEARTBEAT'

	if not bandwidth:
		raise ValueError(f"{source} must be set in .env file.")

	# Persist the chosen quote bandwidth
	_update_env_file({'QUOTE_BANDWIDTH': bandwidth})
	os.environ['QUOTE_BANDWIDTH'] = bandwidth

	print(f"Egress IP: {egress_ip_n}, LUMEN_IP: {lumen_ip_n}")
	print(f"Match: {egress_ip_n == lumen_ip_n}, QUOTE_BANDWIDTH set to: {bandwidth}")

	return bandwidth



def price_request():
	"""
	Send a price request to the Lumen API using env values and print only the id from the response.
	"""
	load_dotenv()

	url = f"{base_url}/Product/v1/priceRequest"
	customer_number = os.getenv('CUSTOMER_NUMBER')
	currency_code = os.getenv('CURRENCY_CODE')
	master_site_id = os.getenv('MASTER_SITE_ID')
	partner_id = os.getenv('PARTNER_ID')
	quote_bandwidth = os.getenv('QUOTE_BANDWIDTH')
	product_code = os.getenv('PRODUCT_CODE')
	product_name = os.getenv('PRODUCT_NAME')
	access_token = os.getenv('ACCESS_TOKEN')

	if not all([customer_number, currency_code, master_site_id, partner_id, quote_bandwidth, product_code, product_name, access_token]):
		raise ValueError("Missing required environment variables for price request.")

	payload = json.dumps({
		"sourceSystem": "NaaS ExternalApi",
		"customerPriceRequestDescription": "NaaS Price Request",
		"customerPurchaseOrderNumber": "",
		"customerNumber": customer_number,
		"currencyCode": currency_code,
		"masterSiteId": master_site_id,
		"productCode": product_code,
		"partnerId": partner_id,
		"productName": product_name,
		"speed": quote_bandwidth
	})
	headers = {
		'x-customer-number': customer_number,
		'Content-Type': 'application/json',
		'Authorization': f'Bearer {access_token}'
	}

	response = requests.post(url, headers=headers, data=payload)
	try:
		response.raise_for_status()
	except requests.HTTPError:
		print(f"Price request failed: {response.status_code} {response.text}")
		raise

	try:
		data = response.json()
	except ValueError:
		print(response.text)
		return

	quote_id = data.get('id')
	if quote_id:
		_update_env_file({'QUOTE_ID': quote_id})
		os.environ['QUOTE_ID'] = quote_id
	print(quote_id)

def order_request():
	"""
	Place an order request using env variables and static values as described.
	"""

	url = f"{base_url}/Customer/v3/Ordering/orderRequest"
	access_token = os.getenv('ACCESS_TOKEN')
	customer_number = os.getenv('CUSTOMER_NUMBER')
	billing_account_id = os.getenv('BILLING_ACCOUNT_ID')
	billing_account_name = os.getenv('BILLING_ACCOUNT_NAME')
	external_id_prefix = os.getenv('EXTERNAL_ID_PREFIX')
	quote_id = os.getenv('QUOTE_ID')
	service_id = os.getenv('SERVICE_ID')
	product_code = '718'
	product_name = 'Internet On-Demand'
	contact_name = os.getenv('CONTACT_NAME')
	contact_role = os.getenv('CONTACT_ROLE')
	contact_email = os.getenv('CONTACT_EMAIL')
	contact_org = os.getenv('CONTACT_ORG')
	contact_phone = os.getenv('CONTACT_PHONE')

	if not all([access_token, customer_number, billing_account_id, billing_account_name, quote_id, service_id, product_code, product_name]):
		raise ValueError("Missing required environment variables for order request.")

	# Generate externalId: prefix + unique string, max 20 chars
	suffix = str(int(time.time()))
	max_len = 20
	allowed_suffix_len = max_len - len(external_id_prefix)
	if allowed_suffix_len <= 0:
		external_id = external_id_prefix[:max_len]
	else:
		external_id = external_id_prefix + suffix[-allowed_suffix_len:]
	external_id = external_id[:20]

	payload = json.dumps({
		"externalId": external_id,
		"billingAccount": {
			"id": billing_account_id,
			"name": billing_account_name
		},
		"channel": [
			{
				"id": 99,
				"name": "NaaS ExternalApi"
			}
		],
		"note": [
			{
				"text": "Change"
			}
		],
		"productOrderItem": [
			{
				"id": service_id,
				"quantity": 1,
				"action": "modify",
				"product": {
					"id": service_id,
					"productCharacteristic": [],
					"productSpecification": {
						"id": "5001",
						"name": "NaaS Internet"
					}
				},
				"productOffering": {
					"id": product_code,
					"name": product_name
				}
			}
		],
		"quote": [
			{
				"id": quote_id,
				"name": quote_id
			}
		],
		"relatedContactInformation": [
			{
				"number": contact_phone,
				"emailAddress": contact_email,
				"role": contact_role,
				"organization": contact_org,
				"name": contact_name,
				"numberExtension": ""
			}
		]
	})
	headers = {
		'x-customer-number': customer_number,
		'Content-Type': 'application/json',
		'Authorization': f'Bearer {access_token}'
	}

	response = requests.post(url, headers=headers, data=payload)
	try:
		response.raise_for_status()
	except requests.HTTPError:
		print(f"Order request failed: {response.status_code} {response.text}")
		raise

	print(response.text)

def main():
	"""
	Main workflow: check inventory, compare SERVICE_BANDWIDTH with QUOTE_BANDWIDTH.
	
	If SERVICE_BANDWIDTH != QUOTE_BANDWIDTH, request a price quote and end.
	If they are the same, no quote is requested.
	
	Requires .env file with:
	- USERNAME, SECRET (OAuth credentials)
	- CUSTOMER_NUMBER
	- SERVICE_ID (or passed as argument)
	- CURRENCY_CODE, PARTNER_ID (for quoting)
	- PRODUCT_CODE, PRODUCT_NAME (for quoting)
	- QUOTE_BANDWIDTH (set via set_quote_bandwidth())
	"""

	try:
		# Ensure access token is available before all steps
		access_token = os.getenv('ACCESS_TOKEN') or get_valid_access_token()
		# Step 1: Check inventory
		print("=" * 50)
		print("Step 1: Checking inventory...")
		print("=" * 50)
		check_inventory()
		print(f"Inventory check complete.\n")

		# Step 2: Set quote bandwidth based on egress IP
		print("=" * 50)
		print("Step 2: Setting quote bandwidth...")
		print("=" * 50)
		set_quote_bandwidth()
		print()

		# Step 3: Compare SERVICE_BANDWIDTH with QUOTE_BANDWIDTH
		load_dotenv()
		quote_bandwidth = os.getenv('QUOTE_BANDWIDTH')
		service_bandwidth = os.getenv('SERVICE_BANDWIDTH')

		print("=" * 50)
		print("Step 3: Comparing bandwidth values...")
		print("=" * 50)
		print(f"SERVICE_BANDWIDTH: {service_bandwidth}")
		print(f"QUOTE_BANDWIDTH: {quote_bandwidth}")

		if service_bandwidth == quote_bandwidth:
			print("Bandwidths match. No quote needed.\n")
			return 0

		print("Bandwidths differ. Requesting price quote...\n")


		# Step 4: Request price quote (only if bandwidths differ)
		print("=" * 50)
		print("Step 4: Requesting price quote...")
		print("=" * 50)
		price_request()
		print(f"Price quote requested successfully. \n")

		# Step 5: Place order based on quote
		print("=" * 50)
		print("Step 5: Placing order based on quote...")
		print("=" * 50)
		order_request()
		print(f"Order placed successfully based on quote {os.getenv('QUOTE_ID')}.\n")



	except Exception as e:
		print(f"Error: {e}")
		return 1

	return 0


if __name__ == '__main__':
	
	exit(main())