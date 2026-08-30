#!/usr/bin/env python3
"""
Test script to simulate normal user flow in the EcommerceAtacadao API.
Tests: user registration, login, product browsing, cart management, order creation, and shipping calculation.
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any, Optional
import httpx

# Test configuration
BASE_URL = "http://localhost:8000"
API_V1_PREFIX = "/api/v1"

class EcommerceAPITester:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=30.0)
        self.admin_token: Optional[str] = None
        self.user_token: Optional[str] = None
        self.admin_user_data: Optional[Dict[str, Any]] = None
        self.user_user_data: Optional[Dict[str, Any]] = None
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
        
    def _auth_headers(self, token: Optional[str] = None) -> Dict[str, str]:
        """Generate authorization headers."""
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}
        
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        token: Optional[str] = None,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> httpx.Response:
        """Make HTTP request with error handling."""
        url = f"{API_V1_PREFIX}{endpoint}"
        headers = self._auth_headers(token)
        
        try:
            response = await self.client.request(
                method, 
                url, 
                headers=headers, 
                json=json_data,
                params=params
            )
            return response
        except Exception as e:
            print(f"Request failed: {e}")
            raise
            
    async def test_health_check(self) -> bool:
        """Test if the API is running."""
        try:
            response = await self.client.get("/health")
            if response.status_code == 200:
                print("✓ Health check passed")
                return True
            else:
                print(f"✗ Health check failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"✗ Health check error: {e}")
            return False
            
    async def test_admin_login(self) -> bool:
        """Test admin user login using seed data."""
        try:
            login_data = {
                "email": "admin@atacadaocenter.com.br",
                "password": "Admin123!"
            }
            
            response = await self._make_request(
                "POST", 
                "/auth/login", 
                json_data=login_data
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("data", {}).get("access_token")
                if self.admin_token:
                    print("✓ Admin login successful")
                    return True
                else:
                    print("✗ Admin login failed: No access token in response")
                    return False
            else:
                print(f"✗ Admin login failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"✗ Admin login error: {e}")
            return False
            
    async def test_user_login(self) -> bool:
        """Test regular user login using seed data."""
        try:
            login_data = {
                "email": "cliente1@example.com",
                "password": "Cliente123!"
            }
            
            response = await self._make_request(
                "POST", 
                "/auth/login", 
                json_data=login_data
            )
            
            if response.status_code == 200:
                data = response.json()
                self.user_token = data.get("data", {}).get("access_token")
                if self.user_token:
                    print("✓ User login successful")
                    return True
                else:
                    print("✗ User login failed: No access token in response")
                    return False
            else:
                print(f"✗ User login failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"✗ User login error: {e}")
            return False
            
    async def test_get_current_user(self, token: str, user_type: str) -> bool:
        """Test getting current user info."""
        if not token:
            print(f"✗ {user_type} token is missing, skipping test")
            return False
        try:
            response = await self._make_request(
                "GET", 
                "/users/me", 
                token=token
            )
            
            if response.status_code == 200:
                data = response.json()
                user_data = data.get("data", {})
                print(f"✓ {user_type} user info retrieved: {user_data.get('email')}")
                if user_type == "Admin":
                    self.admin_user_data = user_data
                else:
                    self.user_user_data = user_data
                return True
            else:
                print(f"✗ {user_type} get current user failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"✗ {user_type} get current user error: {e}")
            return False
            
    async def test_list_products(self) -> bool:
        """Test listing products."""
        try:
            response = await self._make_request("GET", "/catalog/products/")
            
            if response.status_code == 200:
                data = response.json()
                products = data.get("data", [])
                print(f"✓ Products list retrieved: {len(products)} products")
                return len(products) > 0
            else:
                print(f"✗ Products list failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"✗ Products list error: {e}")
            return False
            
    async def test_get_product_details(self, product_code: str) -> bool:
        """Test getting product details."""
        try:
            response = await self._make_request("GET", f"/catalog/products/{product_code}")
            
            if response.status_code == 200:
                data = response.json()
                product = data.get("data", {})
                print(f"✓ Product details retrieved: {product.get('name')}")
                return True
            else:
                print(f"✗ Product details failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"✗ Product details error: {e}")
            return False
            
    async def test_get_cart(self, token: str) -> bool:
        """Test getting user cart."""
        if not token:
            print("✗ User token is missing, skipping cart test")
            return False
        try:
            response = await self._make_request("GET", "/cart/", token=token)
            
            if response.status_code == 200:
                data = response.json()
                cart = data.get("data", {})
                items_count = len(cart.get("items", []))
                print(f"✓ Cart retrieved: {items_count} items")
                return True
            else:
                print(f"✗ Cart retrieval failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"✗ Cart retrieval error: {e}")
            return False
            
    async def test_add_to_cart(self, token: str, variant_id: int, quantity: int = 1) -> bool:
        """Test adding item to cart."""
        if not token:
            print("✗ User token is missing, skipping add to cart test")
            return False
        try:
            cart_item_data = {
                "variant_id": variant_id,
                "quantity": quantity
            }
            
            response = await self._make_request(
                "POST", 
                "/cart/items", 
                token=token,
                json_data=cart_item_data
            )
            
            if response.status_code in [200, 201]:
                print(f"✓ Item added to cart: variant {variant_id}, quantity {quantity}")
                return True
            else:
                print(f"✗ Add to cart failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"✗ Add to cart error: {e}")
            return False
            
    async def test_create_order(self, token: str) -> bool:
        """Test creating an order from cart."""
        if not token:
            print("✗ User token is missing, skipping order creation test")
            return False
        try:
            # First get cart to see what's in it
            cart_response = await self._make_request("GET", "/cart/", token=token)
            if cart_response.status_code != 200:
                print("✗ Could not retrieve cart for order creation")
                return False
                
            cart_data = cart_response.json().get("data", {})
            items = cart_data.get("items", [])
            
            if not items:
                print("✗ Cart is empty, cannot create order")
                return False
                
            # Create order
            order_data = {}  # Empty as it should use cart contents
            
            response = await self._make_request(
                "POST", 
                "/sales/orders/", 
                token=token,
                json_data=order_data
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                order = data.get("data", {})
                print(f"✓ Order created: {order.get('id')} - Status: {order.get('status')}")
                return True
            else:
                print(f"✗ Order creation failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"✗ Order creation error: {e}")
            return False
            
    async def test_list_orders(self, token: str) -> bool:
        """Test listing user orders."""
        if not token:
            print("✗ User token is missing, skipping orders list test")
            return False
        try:
            response = await self._make_request("GET", "/sales/orders/", token=token)
            
            if response.status_code == 200:
                data = response.json()
                orders = data.get("data", [])
                print(f"✓ Orders list retrieved: {len(orders)} orders")
                return True
            else:
                print(f"✗ Orders list failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"✗ Orders list error: {e}")
            return False
            
    async def test_shipping_calculation(self) -> bool:
        """Test shipping calculation endpoint."""
        try:
            # Test data for shipping calculation
            shipping_data = {
                "origin_zip_code": "01001000",  # São Paulo
                "destination_zip_code": "20040020",  # Rio de Janeiro
                "items": [
                    {
                        "variant_id": 1,  # Assuming variant ID 1 exists from seed
                        "quantity": 1
                    }
                ]
            }
            
            response = await self._make_request(
                "POST", 
                "/operations/shipping/calculate", 
                json_data=shipping_data
            )
            
            if response.status_code == 200:
                data = response.json()
                quotes = data.get("data", [])
                print(f"✓ Shipping calculation successful: {len(quotes)} quotes retrieved")
                if quotes:
                    print(f"  Cheapest quote: {quotes[0].get('price')} for {quotes[0].get('service_name')}")
                return True
            else:
                print(f"✗ Shipping calculation failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"✗ Shipping calculation error: {e}")
            return False
            
    async def run_all_tests(self):
        """Run all tests in sequence."""
        print("=" * 60)
        print("Starting EcommerceAtacadao API User Flow Tests")
        print("=" * 60)
        
        # Test 1: Health check
        if not await self.test_health_check():
            print("API is not accessible. Stopping tests.")
            return
            
        print("\n--- Authentication Tests ---")
        # Test 2: Admin login
        admin_login_ok = await self.test_admin_login()
        if admin_login_ok:
            await self.test_get_current_user(self.admin_token or "", "Admin")
            
        # Test 3: User login
        user_login_ok = await self.test_user_login()
        if user_login_ok:
            await self.test_get_current_user(self.user_token or "", "User")
            
        print("\n--- Product Tests ---")
        # Test 4: List products
        await self.test_list_products()
        
        # Test 5: Get product details (if we have products)
        if admin_login_ok or user_login_ok:
            # Try to get a known product from seed data
            await self.test_get_product_details("DET-5L-UN")  # Detergente Neutro 5L
            
        print("\n--- Cart Tests ---")
        # Test 6: Get cart (user)
        if user_login_ok:
            await self.test_get_cart(self.user_token or "")
            
        print("\n--- Order Tests ---")
        # Test 7: Create order (user)
        if user_login_ok:
            await self.test_create_order(self.user_token or "")
            await self.test_list_orders(self.user_token or "")
            
        print("\n--- Shipping Tests ---")
        # Test 8: Shipping calculation
        await self.test_shipping_calculation()
        
        print("\n" + "=" * 60)
        print("Tests Completed")
        print("=" * 60)

async def main():
    """Main test runner."""
    async with EcommerceAPITester() as tester:
        await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())