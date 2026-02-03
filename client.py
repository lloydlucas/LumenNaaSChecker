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

def get_access_token():
	load_dotenv()
	url = "https://api.lumen.com/oauth/v2/token"
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
		if access_token:
			# Overwrite ACCESS_TOKEN in .env file
			env_path = '.env'
			lines = []
			with open(env_path, 'r') as env_file:
				lines = env_file.readlines()
			with open(env_path, 'w') as env_file:
				found = False
				for line in lines:
					if line.startswith('ACCESS_TOKEN='):
						env_file.write(f"ACCESS_TOKEN={access_token}\n")
						found = True
					else:
						env_file.write(line)
				if not found:
					env_file.write(f"ACCESS_TOKEN={access_token}\n")
			print(f"ACCESS_TOKEN value '{access_token}' updated in .env")
		else:
			print("No access token found in response.")
	else:
		print(f"Failed to get token: {response.status_code} {response.text}")

if __name__ == "__main__":
	get_access_token()
	egress_ip = get_egress_ip()
