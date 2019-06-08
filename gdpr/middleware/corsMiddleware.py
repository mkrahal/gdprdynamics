# This middleware is essentail in order to allow communication between the server where your app is registered and requests comming from merchants
# that have installed your app. 
# Since your app is rendered as an emmbeded app within the admin panel of your merhant's backends, requests from your app will originate from the 
# merchant's store domain and not the domain where your app is hosted which will raise CORS flags and thus be rejected.

# Example: if your app is hosted at abc.com, once it is rendered as an embedded app in the merchant's backend hosted at merchant.myshopify.com 
# and the app attempts to sends a request back to its host server (abc.com), that request will come from merchant.myshopify.com (not abc.com); 
# which will be rejected due to CORS limitations. 

# In order to bypass this limitation, the middleware below allows the domains specified in the response["Access-Control-Allow-Origin"] 
# dictionnary to request resources fromthe app's host server even though they are not from the same domain origin. 
# note: only the domains listed here will be allowed all others will be rejected 

class corsMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Access-Control-Allow-Origin"] = "*"  # Change this to allow only registered merchant store's domains to make requests
        response["Access-Control-Allow-Headers"] =  "Origin, X-Requested-With, Content-Type, Accept, X-Shopify-Web"

        return response
