import hashlib, base64, hmac


# String query recieved using request.body: 
"""
GET '/?hmac=56f5d3bb7ff8d062001d4e5f3065d391adf271a761dc48b2dbc0ea44f7be582e&locale=en&protocol=https%3A%2F%2F&shop=jerrysjerseystore.myshopify.com&timestamp=1525217007'
"""

hmac_to_verify = '4712bf92ffc2917d15a2f5a273e39f0116667419aa4b6ac0b3baaf26fa3c4d20'
secret = '80728c3d7509dd1d34c374852f6a0f20'
#body = "locale=en&protocol=https://&shop=jerrysjerseystore.myshopify.com&timestamp=1525217007"

body = "locale=en&protocol=https://&shop=jerrysjerseystore.myshopify.com&timestamp=1525223379"

h = hmac.new(secret, body, hashlib.sha256)
print(h.hexdigest())



"""
Step:1

First we need to get the parameters except hmac parameter.
Note: we need all the parameters sent by shopify server.

 

Step:2

keys and values must be checked for & an % characters if found then it should be replaced by %25 and %26 respectively.
if key contains = character then it should be replaced by %3d which is nothing but utf-8 value of the character.
 

Step:3

Then build a string in which key and value are joined together using = character and such key and value pair joined by & sign .
sorted in alphabetical order by key name
 

Step:4

Finally we need to calculate  hmac-sha256 hash using app-secret-key as the key .
the calculated hash digest can be checked with hmac value as provided by the shopify.
"""
