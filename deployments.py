import requests
import re
import sys
from typing import List, Tuple, Optional

def get_github_file_content(repo: str, file_path: str, github_base_url: str) -> Optional[str]:
    """
    Fetch file content from GitHub repository using the raw content URL.
    
    Args:
        repo: Repository name (just the repo name, not owner/repo)
        file_path: Path to the file in the repository
        github_base_url: Base GitHub URL for your organization
        
    Returns:
        File content as string or None if not found
    """
    # For enterprise GitHub, the raw URL format is typically:
    # https://your-github-domain/raw/org/repo/branch/path
    url = f"{github_base_url}/raw/{repo}/main/{file_path}"
    
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            return response.text
        else:
            print(f"Error: Could not fetch {file_path} from {repo} (Status: {response.status_code})")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {file_path} from {repo}: {str(e)}")
        return None

def extract_build_number(content: str) -> Optional[str]:
    """
    Extract the build number from content that contains 'build: ' pattern.
    
    Args:
        content: File content to search
        
    Returns:
        Build number as string or None if not found
    """
    # Look for lines containing 'build: ' and extract numbers after it
    pattern = r'build:\s*([0-9]+(?:\.[0-9]+)*)'
    
    for line in content.split('\n'):
        if 'build:' in line.lower():
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                return match.group(1)
    
    return None

def process_regions_and_repos(from_region: str, to_regions: List[str], from_env: str, to_env: str, github_base_url: str, org_name: str):
    """
    Process the regions and fetch build information from both repositories.
    
    Args:
        from_region: Source region
        to_regions: List of target regions
        from_env: Source environment
        to_env: Target environment
        github_base_url: Base GitHub URL for your organization
        org_name: GitHub organization name
    """
    repositories = [
        "catalyst-policy-api",
        "catalyst-crm-api"
    ]
    
    print(f"Configuration:")
    print(f"From Region: {from_region}")
    print(f"To Regions: {', '.join(to_regions)}")
    print(f"From Environment: {from_env}")
    print(f"To Environment: {to_env}")
    print(f"GitHub URL: {github_base_url}")
    print(f"Organization: {org_name}")
    print("-" * 50)
    
    # Process the fromEnv_fromRegion file
    filename = f"flo_{from_env}_{from_region}"
    print(f"\nSearching for file: {filename}")
    
    for repo in repositories:
        repo_full_path = f"{org_name}/{repo}"
        print(f"\nChecking repository: {repo_full_path}")
        
        # Try common file extensions and locations
        possible_paths = [
            filename,
            f"{filename}.yml",
            f"{filename}.yaml",
            f"config/{filename}",
            f"config/{filename}.yml",
            f"config/{filename}.yaml",
            f"configs/{filename}",
            f"configs/{filename}.yml",
            f"configs/{filename}.yaml"
        ]
        
        found = False
        for path in possible_paths:
            content = get_github_file_content(repo_full_path, path, github_base_url)
            if content:
                build_number = extract_build_number(content)
                if build_number:
                    print(f"✓ Found in {repo_full_path}/{path}")
                    print(f"  Build number: {build_number}")
                    found = True
                    break
                else:
                    print(f"✓ Found file {repo_full_path}/{path} but no 'build:' line with numbers")
                    found = True
                    break
        
        if not found:
            print(f"✗ File {filename} not found in {repo_full_path}")

def main():
    """
    Main function to get user input and process the repositories.
    """
    try:
        # Configuration for your organization's GitHub
        print("GitHub Configuration Setup")
        github_base_url = input("Enter your GitHub base URL (e.g., https://github.yourcompany.com): ").strip()
        org_name = input("Enter your organization name: ").strip()
        
        if not github_base_url or not org_name:
            print("Error: GitHub URL and organization name are required!")
            return
        
        # Remove trailing slash from URL if present
        github_base_url = github_base_url.rstrip('/')
        
        print("\n" + "="*50)
        
        # Get input from user
        from_region = input("Enter fromRegion: ").strip()
        to_regions_input = input("Enter toRegions (comma-separated): ").strip()
        from_env = input("Enter fromEnv: ").strip()
        to_env = input("Enter toEnv: ").strip()
        
        # Validate inputs
        if not all([from_region, to_regions_input, from_env, to_env]):
            print("Error: All fields are required!")
            return
        
        # Parse comma-separated regions
        to_regions = [region.strip() for region in to_regions_input.split(",") if region.strip()]
        
        if not to_regions:
            print("Error: At least one toRegion is required!")
            return
        
        # Process the repositories
        process_regions_and_repos(from_region, to_regions, from_env, to_env, github_base_url, org_name)
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    # Example usage with hardcoded values for testing
    # Uncomment the lines below and comment out main() to use hardcoded values
    
    # github_base_url = "https://github.yourcompany.com"  # Replace with your GitHub URL
    # org_name = "your-org-name"  # Replace with your organization name
    # from_region = "us-east-1"
    # to_regions = ["us-west-2", "eu-west-1"]
    # from_env = "prod"
    # to_env = "staging"
    # process_regions_and_repos(from_region, to_regions, from_env, to_env, github_base_url, org_name)
    
    main()