#!/usr/bin/env python3
"""
Simple test script for ZAI Vision MCP tools.
Requires: Z_AI_API_KEY environment variable to be set.
"""

import os


def check_api_key():
    """Check if ZAI API key is set in environment."""
    api_key = os.getenv("Z_AI_API_KEY")
    if api_key == "YOUR_ZAI_API_KEY" or not api_key:
        print("Warning: Z_AI_API_KEY environment variable is not set or is placeholder.")
        print("   Please set it: export Z_AI_API_KEY='your-actual-api-key'")
        return False
    return True


def print_usage_examples():
    """Print example usage of ZAI MCP tools."""
    print("\n" + "="*60)
    print("ZAI Vision MCP Server - Available Tools")
    print("="*60)

    examples = [
        ("analyze_image", "General image analysis", "Analyze a screenshot and describe contents"),
        ("analyze_video", "Video analysis", "Extract key moments from MP4/MOV videos"),
        ("analyze_data_visualization", "Chart/graph analysis", "Extract insights from charts and dashboards"),
        ("diagnose_error_screenshot", "Error diagnosis", "Understand error messages and stack traces"),
        ("extract_text_from_screenshot", "OCR", "Extract text from images/code/terminals"),
        ("ui_diff_check", "UI comparison", "Compare expected vs actual UI screenshots"),
        ("ui_to_artifact", "UI to code", "Convert UI mockup to frontend code"),
        ("understand_technical_diagram", "Diagram analysis", "Understand architecture/flow/UML diagrams"),
    ]

    for tool, description, use_case in examples:
        print(f"\n[+] {tool}")
        print(f"    Description: {description}")
        print(f"    Use case: {use_case}")

    print("\n" + "="*60)
    print("\nTo use these tools, call them via Claude Code or your MCP client.")
    print("Example in Claude Code:")
    print('  - Analyze this image: /path/to/screenshot.png')
    print('  - Extract text from: /path/to/code-screenshot.png')
    print('  - Convert this UI to code: /path/to/mockup.png')


def main():
    print("ZAI Vision MCP Server Test Script")
    print("-" * 40)

    if not check_api_key():
        print("\nPlease configure your API key in:")
        print("  1. Environment: export Z_AI_API_KEY='your-key'")
        print("  2. Or in agent_framework/config/mcp.json")

    print_usage_examples()

    print("\n" + "="*60)
    print("Quick Test - Describe what you want to test:")
    print("="*60)
    print("\nIn Claude Code, you can directly use MCP tools like:")
    print('  @mcp__zai-mcp-server__analyze_image with image_source=path/to/image')
    print('  @mcp__zai-mcp-server__extract_text_from_screenshot with image_source=path/to/image')
    print("\nNote: ZAI API key must be configured in mcp.json or environment.")


if __name__ == "__main__":
    main()
