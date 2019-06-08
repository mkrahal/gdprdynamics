import shopify

def current_shop(request):
    if not shopify.ShopifyResource.site:
        return {'current_shop': None}

    # Added try/except block to handle uninstall error 
    try:
        return {'current_shop': shopify.Shop.current()}
    except Exception:
        return  {'current_shop': None}
