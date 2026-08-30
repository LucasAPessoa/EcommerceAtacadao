#!/usr/bin/env python3
"""
Route validation test for EcommerceAtacadao API.
Tests the API route structures and basic validation without requiring a running server.
"""

import sys
import os
from typing import List, Dict, Any

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_route_imports():
    """Test that all route modules can be imported successfully."""
    print("Testing route imports...")
    
    try:
        # Test main API router
        from src.api.v1.endpoints.router import api_router
        print("✓ Main API router imported successfully")
        
        # Test auth routes
        from src.api.v1.endpoints.identity.auth import router as auth_router
        print("✓ Auth router imported successfully")
        
        # Test user routes
        from src.api.v1.endpoints.identity.users import router as users_router
        print("✓ Users router imported successfully")
        
        # Test address routes
        from src.api.v1.endpoints.identity.addresses import router as addresses_router
        print("✓ Addresses router imported successfully")
        
        # Test catalog routes
        from src.api.v1.endpoints.catalog.router import catalog_router
        print("✓ Catalog router imported successfully")
        
        # Test product routes
        from src.api.v1.endpoints.catalog.product import router as product_router
        print("✓ Product router imported successfully")
        
        # Test category routes
        from src.api.v1.endpoints.catalog.category import router as category_router
        print("✓ Category router imported successfully")
        
        # Test sales routes
        from src.api.v1.endpoints.sales.router import sales_router
        print("✓ Sales router imported successfully")
        
        # Test cart routes
        from src.api.v1.endpoints.sales.cart import router as cart_router
        print("✓ Cart router imported successfully")
        
        # Test order routes
        from src.api.v1.endpoints.sales.order import router as order_router
        print("✓ Order router imported successfully")
        
        # Test operations routes
        from src.api.v1.endpoints.operations.router import operations_router
        print("✓ Operations router imported successfully")
        
        # Test shipping routes
        from src.api.v1.endpoints.operations.shipping import router as shipping_router
        print("✓ Shipping router imported successfully")
        
        return True
        
    except Exception as e:
        print(f"✗ Route import failed: {e}")
        return False

def test_schema_imports():
    """Test that schema modules can be imported successfully."""
    print("\nTesting schema imports...")
    
    try:
        # Test auth schemas
        from src.schemas.identity.user_schema import (
            UserCreate, UserLogin, Token, UserResponse, RefreshTokenRequest
        )
        print("✓ Auth schemas imported successfully")
        
        # Test cart schemas
        from src.schemas.sales.cart_schema import (
            CartItemCreateSchema, CartItemUpdateSchema, CartResponseSchema
        )
        print("✓ Cart schemas imported successfully")
        
        # Test order schemas
        from src.schemas.sales.order_schema import (
            OrderCreateSchema, OrderResponseSchema
        )
        print("✓ Order schemas imported successfully")
        
        # Test product schemas
        from src.schemas.catalog.product_schema import (
            ProductCreateSchema, ProductResponseSchema
        )
        print("✓ Product schemas imported successfully")
        
        # Test product variant schemas
        from src.schemas.catalog.product_variant_schema import (
            ProductVariantCreateSchema, ProductVariantResponseSchema
        )
        print("✓ Product variant schemas imported successfully")
        
        # Test category schemas
        from src.schemas.catalog.category_schema import (
            CategoryCreateSchema, CategoryResponseSchema
        )
        print("✓ Category schemas imported successfully")
        
        # Test shipping schemas
        from src.schemas.operations.shipping_schema import (
            ShippingCalculateItemSchema, ShippingQuoteSchema
        )
        print("✓ Shipping schemas imported successfully")
        
        return True
        
    except Exception as e:
        print(f"✗ Schema import failed: {e}")
        return False

def test_service_imports():
    """Test that service modules can be imported successfully."""
    print("\nTesting service imports...")
    
    try:
        # Test auth service
        from src.services.identity.auth_service import AuthService
        print("✓ Auth service imported successfully")
        
        # Test cart service
        from src.services.sales.cart_service import CartService
        print("✓ Cart service imported successfully")
        
        # Test order service
        from src.services.sales.order_service import OrderService
        print("✓ Order service imported successfully")
        
        # Test product service
        from src.services.catalog.product_service import ProductService
        print("✓ Product service imported successfully")
        
        # Test shipping service
        from src.services.operations.shipping_service import ShippingService
        print("✓ Shipping service imported successfully")
        
        return True
        
    except Exception as e:
        print(f"✗ Service import failed: {e}")
        return False

def test_model_imports():
    """Test that model modules can be imported successfully."""
    print("\nTesting model imports...")
    
    try:
        # Test identity models
        from src.models.identity import User, Role, RefreshToken
        print("✓ Identity models imported successfully")
        
        # Test catalog models
        from src.models.catalog import Product, ProductVariant, Category
        print("✓ Catalog models imported successfully")
        
        # Test sales models
        from src.models.sales import Order, OrderItem, Cart, CartItem
        print("✓ Sales models imported successfully")
        
        # Test operations models
        from src.models.operations import Transaction
        print("✓ Operations models imported successfully")
        
        return True
        
    except Exception as e:
        print(f"✗ Model import failed: {e}")
        return False

def test_repository_imports():
    """Test that repository modules can be imported successfully."""
    print("\nTesting repository imports...")
    
    try:
        # Test identity repositories
        from src.repositories.identity.user_repository import UserRepository
        from src.repositories.identity.refresh_token_repository import RefreshTokenRepository
        print("✓ Identity repositories imported successfully")
        
        # Test catalog repositories
        from src.repositories.catalog.product_variant_repository import ProductVariantRepository
        from src.repositories.catalog.product_repository import ProductRepository
        from src.repositories.catalog.category_repository import CategoryRepository
        print("✓ Catalog repositories imported successfully")
        
        # Test sales repositories
        from src.repositories.sales.cart_repository import CartRepository
        from src.repositories.sales.order_repository import OrderRepository
        print("✓ Sales repositories imported successfully")
        
        return True
        
    except Exception as e:
        print(f"✗ Repository import failed: {e}")
        return False

def test_config_and_security():
    """Test that config and security modules can be imported."""
    print("\nTesting config and security imports...")
    
    try:
        from src.core.config import settings
        print("✓ Config imported successfully")
        
        from src.core.sec import get_password_hash, verify_token, create_access_token
        print("✓ Security module imported successfully")
        
        from src.core.db import AsyncSessionLocal, engine, get_db
        print("✓ Database module imported successfully")
        
        return True
        
    except Exception as e:
        print(f"✗ Config/security import failed: {e}")
        return False

def count_routes_in_router(router) -> int:
    """Count the number of routes in a router."""
    count = 0
    if hasattr(router, 'routes'):
        for route in router.routes:
            if hasattr(route, 'path'):
                count += 1
            # Handle mounted routers
            if hasattr(route, 'router') and hasattr(route.router, 'routes'):
                count += count_routes_in_router(route.router)
    return count

def test_route_counting():
    """Test counting routes in the main API router."""
    print("\nTesting route counting...")
    
    try:
        from src.api.v1.endpoints.router import api_router
        
        total_routes = count_routes_in_router(api_router)
        print(f"✓ Total API routes counted: {total_routes}")
        
        # Breakdown by domain
        from src.api.v1.endpoints.identity.auth import router as auth_router
        from src.api.v1.endpoints.identity.users import router as users_router
        from src.api.v1.endpoints.identity.addresses import router as addresses_router
        from src.api.v1.endpoints.catalog.router import catalog_router
        from src.api.v1.endpoints.sales.router import sales_router
        from src.api.v1.endpoints.operations.router import operations_router
        
        auth_routes = count_routes_in_router(auth_router)
        user_routes = count_routes_in_router(users_router)
        address_routes = count_routes_in_router(addresses_router)
        catalog_routes = count_routes_in_router(catalog_router)
        sales_routes = count_routes_in_router(sales_router)
        operations_routes = count_routes_in_router(operations_router)
        
        print(f"  - Auth routes: {auth_routes}")
        print(f"  - User routes: {user_routes}")
        print(f"  - Address routes: {address_routes}")
        print(f"  - Catalog routes: {catalog_routes}")
        print(f"  - Sales routes: {sales_routes}")
        print(f"  - Operations routes: {operations_routes}")
        
        return True
        
    except Exception as e:
        print(f"✗ Route counting failed: {e}")
        return False

def main():
    """Main test function."""
    print("=" * 70)
    print("EcommerceAtacadao API Route Validation Tests")
    print("=" * 70)
    
    tests = [
        test_route_imports,
        test_schema_imports,
        test_service_imports,
        test_model_imports,
        test_repository_imports,
        test_config_and_security,
        test_route_counting
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()  # Add spacing between tests
    
    print("=" * 70)
    print(f"TEST RESULTS: {passed}/{total} test groups passed")
    
    if passed == total:
        print("🎉 All tests passed! The API structure is valid.")
        return 0
    else:
        print("❌ Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())