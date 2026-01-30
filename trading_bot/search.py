import requests

searchFor = ""  #CONTRACT ADDRESS

url = "https://lite-api.jup.ag/ultra/v1/search?query=" + searchFor

payload = {}
headers = {
  'Accept': 'application/json'
}

response = requests.request("GET", url, headers=headers, data=payload)

data = response.json()

print(data)

for item in data:
    #print(item)
    print("id:", item['id'])
    print("name:", item['name'])
    print("symbol:", item['symbol'])
    print("mcap:", item['mcap'])
#rint(response.text)
#print(response.json()[0]['id'])
#print("id:", data[0]['id'])
#print("name:", data[0]['name'])
#print("symbol:", data[0]['symbol'])
#print("mcap:", data[0]['mcap'])