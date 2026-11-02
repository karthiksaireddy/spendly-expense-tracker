#!/usr/bin/env python3
"""MCP Currency Rate Server

A minimal MCP server that provides currency exchange rates.
Uses the free exchangerate-api.com API (no API key required for basic usage).

This server can be used to convert expenses between currencies.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from typing import Any, Dict
import urllib.request
import urllib.error


# Cache rates for 1 hour to avoid hitting the API too often
RATE_CACHE: Dict[str, tuple[Dict[str, float], datetime]] = {}
CACHE_DURATION = timedelta(hours=1)


def fetch_rates(base_currency: str = "USD") -> Dict[str, float]:
    """Fetch exchange rates from exchangerate-api.com.
    
    Args:
        base_currency: The base currency (default: USD)
        
    Returns:
        Dictionary mapping currency codes to exchange rates
        
    Raises:
        urllib.error.URLError: If the API request fails
    """
    # Check cache
    cache_key = base_currency.upper()
    if cache_key in RATE_CACHE:
        rates, timestamp = RATE_CACHE[cache_key]
        if datetime.now() - timestamp < CACHE_DURATION:
            return rates
    
    # Fetch from API
    url = f"https://api.exchangerate-api.com/v4/latest/{base_currency.upper()}"
    
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            rates = data.get('rates', {})
            
            # Cache the result
            RATE_CACHE[cache_key] = (rates, datetime.now())
            return rates
    except urllib.error.URLError as e:
        raise Exception(f"Failed to fetch exchange rates: {e}")


def convert_amount(
    amount: float,
    from_currency: str,
    to_currency: str
) -> float:
    """Convert an amount from one currency to another.
    
    Args:
        amount: The amount to convert
        from_currency: Source currency code (e.g., "USD", "INR")
        to_currency: Target currency code (e.g., "INR", "USD")
        
    Returns:
        The converted amount
        
    Raises:
        ValueError: If currency codes are invalid
        Exception: If the API request fails
    """
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    
    if from_currency == to_currency:
        return amount
    
    rates = fetch_rates(from_currency)
    
    if to_currency not in rates:
        raise ValueError(f"Currency {to_currency} not found in rates")
    
    return amount * rates[to_currency]


def get_supported_currencies() -> list[str]:
    """Get a list of commonly supported currency codes.
    
    This is a static list of major currencies. The actual API supports more.
    """
    return [
        "USD", "EUR", "GBP", "INR", "JPY", "CAD", "AUD", "CHF",
        "CNY", "HKD", "SGD", "KRW", "MXN", "BRL", "RUB", "ZAR"
    ]


# MCP Server Implementation
def handle_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle an MCP request.
    
    The request format follows the MCP JSON-RPC specification.
    """
    method = request.get("method")
    params = request.get("params", {})
    request_id = request.get("id")
    
    try:
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "convert_currency",
                            "description": "Convert an amount from one currency to another",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "amount": {
                                        "type": "number",
                                        "description": "The amount to convert"
                                    },
                                    "from_currency": {
                                        "type": "string",
                                        "description": "Source currency code (e.g., USD, INR)"
                                    },
                                    "to_currency": {
                                        "type": "string",
                                        "description": "Target currency code (e.g., INR, USD)"
                                    }
                                },
                                "required": ["amount", "from_currency", "to_currency"]
                            }
                        },
                        {
                            "name": "get_exchange_rates",
                            "description": "Get current exchange rates for a base currency",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "base_currency": {
                                        "type": "string",
                                        "description": "Base currency code (default: USD)",
                                        "default": "USD"
                                    }
                                }
                            }
                        },
                        {
                            "name": "list_currencies",
                            "description": "Get a list of commonly supported currency codes",
                            "inputSchema": {
                                "type": "object",
                                "properties": {}
                            }
                        }
                    ]
                }
            }
        
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if tool_name == "convert_currency":
                result = convert_amount(
                    arguments["amount"],
                    arguments["from_currency"],
                    arguments["to_currency"]
                )
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({
                                    "converted_amount": result,
                                    "from": arguments["from_currency"],
                                    "to": arguments["to_currency"],
                                    "original": arguments["amount"]
                                })
                            }
                        ]
                    }
                }
            
            elif tool_name == "get_exchange_rates":
                base = arguments.get("base_currency", "USD")
                rates = fetch_rates(base)
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({
                                    "base_currency": base,
                                    "rates": rates,
                                    "timestamp": datetime.now().isoformat()
                                })
                            }
                        ]
                    }
                }
            
            elif tool_name == "list_currencies":
                currencies = get_supported_currencies()
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({
                                    "currencies": currencies
                                })
                            }
                        ]
                    }
                }
            
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Unknown tool: {tool_name}"
                    }
                }
        
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Unknown method: {method}"
                }
            }
    
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32603,
                "message": str(e)
            }
        }


def main():
    """Run the MCP server (stdin/stdout communication)."""
    print("Currency Rate MCP Server started. Waiting for requests...", file=sys.stderr)
    
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            response = handle_request(request)
            print(json.dumps(response))
            sys.stdout.flush()
        except json.JSONDecodeError:
            error_response = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32700,
                    "message": "Parse error"
                }
            }
            print(json.dumps(error_response))
            sys.stdout.flush()


if __name__ == "__main__":
    main()
