#!/usr/bin/env python3
"""
FLO File Sync Script for UAT Branches

This script detects changes to flo_{branch_name} files in pull requests
and replicates those changes to other UAT branches automatically.

==============================================================================
IMPORTANT: THIS SCRIPT CREATES PULL REQUESTS, NOT DIRECT COMMITS!
==============================================================================

Workflow Flow:

    Original PR                  This Script Creates
    ===========                  ===================
    
    feature-123                  sync-branch-na-456
         |                            |
         v                            v
    [uat_emea]  ─────────────>  [uat_na]      (PR #456)
    (flo_uat_emea changed)      (via PR, not direct commit)
         |
         |                       sync-branch-apac-789
         |                            |
         |                            v
         └─────────────────────>  [uat_apac]   (PR #789)
         |                       (via PR, not direct commit)
         |
         |                       sync-branch-latam-012
         |                            |
         └─────────────────────>  [uat_latam]  (PR #012)
                                 (via PR, not direct commit)

Result: Original PR gets a comment with links to PR #456, #789, #012

==============================================================================

Author: GitHub Actions Bot
"""

import os
import sys
import json
import subprocess
from typing import List, Dict, Optional, Tuple
from datetime import datetime


class FLOFileSyncManager:
    """
    Manages the synchronization of FLO files across UAT branches.
    
    This class handles:
    - Detection of changes to flo_{branch_name} files
    - Replication of changes to target branches
    - Creation of pull requests
    - Adding comments to the original PR
    """
    
    # Define all UAT branches that should be kept in sync
    ALL_UAT_BRANCHES = ["uat_na", "uat_emea", "uat_apac", "uat_latam"]
    
    def __init__(self, base_branch: str, current_branch: str, pr_number: Optional[str] = None):
        """
        Initialize the FLO File Sync Manager.
        
        Args:
            base_branch: The base branch of the PR (e.g., 'uat_emea')
            current_branch: The head/source branch of the PR
            pr_number: The pull request number (if triggered by PR event)
        """
        self.base_branch = base_branch
        self.current_branch = current_branch
        self.pr_number = pr_number
        
        # Determine which file to watch based on the base branch
        # For example, if base_branch is 'uat_emea', watch 'flo_uat_emea.yml'
        self.flo_file = f"flo_{base_branch}.yml"
        
        # Calculate target branches (all UAT branches except the base branch)
        self.target_branches = [b for b in self.ALL_UAT_BRANCHES if b != base_branch]
        
        # Storage for created PR information
        self.created_prs: List[Dict[str, str]] = []
        
        print(f"🔧 Initialized FLO File Sync Manager")
        print(f"   Base Branch: {self.base_branch}")
        print(f"   Current Branch: {self.current_branch}")
        print(f"   Watching File: {self.flo_file}")
        print(f"   Target Branches: {', '.join(self.target_branches)}")
    
    def run_command(self, command: List[str], check: bool = True) -> Tuple[int, str, str]:
        """
        Execute a shell command and return the result.
        
        Args:
            command: List of command arguments
            check: Whether to raise exception on non-zero exit code
            
        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        print(f"💻 Running: {' '.join(command)}")
        
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=check
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except subprocess.CalledProcessError as e:
            print(f"❌ Command failed with exit code {e.returncode}")
            print(f"   Error: {e.stderr}")
            if check:
                raise
            return e.returncode, e.stdout, e.stderr
    
    def detect_file_changes(self, commit_sha: str) -> bool:
        """
        Detect if the flo_{branch_name} file was changed in the current PR/commit.
        
        Args:
            commit_sha: The commit SHA to compare against
            
        Returns:
            True if the flo file was changed, False otherwise
        """
        print(f"\n🔍 Detecting changes to {self.flo_file}...")
        
        # Get the list of changed files by comparing with the base branch
        # This shows all files that differ between the base branch and the current commit
        returncode, changed_files, _ = self.run_command([
            "git", "diff", "--name-only",
            f"origin/{self.base_branch}...{commit_sha}"
        ])
        
        if returncode != 0:
            print(f"⚠️  Failed to get changed files")
            return False
        
        # Split the output into individual file paths
        files_list = changed_files.split('\n') if changed_files else []
        
        print(f"📝 Changed files in this PR:")
        for file in files_list:
            print(f"   - {file}")
        
        # Check if our target flo file is in the list of changed files
        file_changed = self.flo_file in files_list
        
        if file_changed:
            print(f"✅ FLO file '{self.flo_file}' was modified")
        else:
            print(f"ℹ️  FLO file '{self.flo_file}' was not modified")
        
        return file_changed
    
    def get_file_content(self, file_path: str) -> Optional[str]:
        """
        Read and return the content of a file.
        
        Args:
            file_path: Path to the file to read
            
        Returns:
            File content as string, or None if file doesn't exist
        """
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            print(f"✅ Successfully read {file_path} ({len(content)} bytes)")
            return content
        except FileNotFoundError:
            print(f"❌ File not found: {file_path}")
            return None
        except Exception as e:
            print(f"❌ Error reading file {file_path}: {e}")
            return None
    
    def write_file_content(self, file_path: str, content: str) -> bool:
        """
        Write content to a file.
        
        Args:
            file_path: Path to the file to write
            content: Content to write to the file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(file_path, 'w') as f:
                f.write(content)
            print(f"✅ Successfully wrote to {file_path} ({len(content)} bytes)")
            return True
        except Exception as e:
            print(f"❌ Error writing file {file_path}: {e}")
            return False
    
    def sync_to_target_branch(self, target_branch: str, file_content: str) -> Optional[str]:
        """
        Sync the FLO file content to a target branch by creating a NEW branch.
        
        IMPORTANT: This method DOES NOT commit directly to the target branch.
        Instead, it follows this flow:
        
        1. Checkout the target branch (e.g., uat_na) as a starting point
        2. Create a NEW sync branch (e.g., sync-flo-from-uat_emea-to-uat_na-123456)
        3. Write the file content to the NEW sync branch
        4. Commit and push changes to the NEW sync branch (NOT to target branch)
        5. Return the sync branch name so a PR can be created later
        
        The actual PR from sync_branch → target_branch is created in create_pull_request()
        
        Args:
            target_branch: The target UAT branch (will be the BASE of the PR)
            file_content: The content to write to the flo file
            
        Returns:
            The name of the created sync branch (will be the HEAD of the PR), 
            or None if no changes needed
        """
        print(f"\n{'='*60}")
        print(f"🔄 Syncing to {target_branch}")
        print(f"⚠️  NOTE: Creating a NEW branch, NOT committing directly!")
        print(f"{'='*60}")
        
        # Fetch the latest version of the target branch from remote
        # We need this as a starting point to create our sync branch
        print(f"📥 Fetching {target_branch}...")
        self.run_command(["git", "fetch", "origin", target_branch])
        
        # Checkout the target branch TEMPORARILY (just to use as a base)
        # We will immediately create a new branch from this point
        print(f"🔀 Checking out {target_branch} (as a starting point)...")
        self.run_command(["git", "checkout", target_branch])
        
        # ============================================================
        # CRITICAL: Create a NEW branch for the PR
        # ============================================================
        # We are NOT committing to the target branch directly!
        # Instead, we create a unique sync branch that will be used
        # as the HEAD (source) branch of the pull request.
        # 
        # Format: sync-flo-from-{source}-to-{target}-{timestamp}
        # Example: sync-flo-from-uat_emea-to-uat_na-1707123456
        # ============================================================
        timestamp = int(datetime.now().timestamp())
        sync_branch = f"sync-flo-from-{self.base_branch}-to-{target_branch}-{timestamp}"
        
        print(f"🌿 Creating NEW sync branch: {sync_branch}")
        print(f"   This branch will be the HEAD of the PR → {target_branch}")
        self.run_command(["git", "checkout", "-b", sync_branch])
        
        # The target file name in this branch (same pattern: flo_{branch_name})
        target_flo_file = f"flo_{target_branch}.yml"
        
        # Write the content to the target flo file
        print(f"📝 Writing content to {target_flo_file}...")
        if not self.write_file_content(target_flo_file, file_content):
            print(f"❌ Failed to write file content")
            return None
        
        # Check if there are actual differences (git diff will be empty if no changes)
        returncode, diff_output, _ = self.run_command(
            ["git", "diff", "--quiet"],
            check=False
        )
        
        # git diff --quiet returns 0 if no differences, 1 if differences exist
        if returncode == 0:
            print(f"ℹ️  No changes needed for {target_branch} (content is already identical)")
            # Clean up: go back to original branch and delete the sync branch
            self.run_command(["git", "checkout", target_branch])
            self.run_command(["git", "branch", "-D", sync_branch])
            return None
        
        # ============================================================
        # Stage and commit changes to the SYNC BRANCH (not target branch!)
        # ============================================================
        print(f"➕ Staging changes in {sync_branch}...")
        self.run_command(["git", "add", target_flo_file])
        
        # Create a descriptive commit message
        commit_message = f"Sync {target_flo_file} from {self.base_branch}\n\n"
        if self.pr_number:
            commit_message += f"Automatically synced changes from PR #{self.pr_number} in {self.base_branch}"
        else:
            commit_message += f"Automatically synced changes from {self.base_branch}"
        
        print(f"💾 Committing changes to {sync_branch} (NOT to {target_branch})...")
        self.run_command(["git", "commit", "-m", commit_message])
        
        # ============================================================
        # Push the SYNC BRANCH to remote (not target branch!)
        # ============================================================
        # This pushes our new sync branch to the remote repository.
        # The target branch remains untouched at this point.
        # A PR will be created in the next step (create_pull_request method)
        # ============================================================
        print(f"🚀 Pushing {sync_branch} to remote (target branch unchanged)...")
        self.run_command(["git", "push", "origin", sync_branch])
        
        print(f"✅ Successfully created sync branch for {target_branch}")
        print(f"   Next step: Create PR from {sync_branch} → {target_branch}")
        return sync_branch
    
    def create_pull_request(self, target_branch: str, sync_branch: str) -> Optional[str]:
        """
        Create a pull request from sync_branch → target_branch.
        
        This is where the magic happens! The PR structure is:
        - BASE branch: target_branch (e.g., uat_na) - where changes will be merged
        - HEAD branch: sync_branch (e.g., sync-flo-from-uat_emea-to-uat_na-123456)
        
        The target branch is NEVER directly modified. All changes go through PR review.
        
        Args:
            target_branch: The BASE branch for the PR (where changes will merge to)
            sync_branch: The HEAD branch with the changes (source of the PR)
            
        Returns:
            The URL of the created PR, or None if creation failed
        """
        print(f"\n{'='*60}")
        print(f"📝 Creating Pull Request")
        print(f"   FROM: {sync_branch} (HEAD)")
        print(f"   TO:   {target_branch} (BASE)")
        print(f"{'='*60}")
        
        # Construct the PR title
        pr_title = f"🔄 Sync flo_{target_branch} from {self.base_branch}"
        
        # Construct a detailed PR body with markdown formatting
        pr_body = f"""## Automated FLO File Sync

This PR automatically syncs changes made to `flo_{target_branch}` from the `{self.base_branch}` branch.

### Source Information
- **Source Branch:** {self.base_branch}
- **Original PR:** #{self.pr_number if self.pr_number else 'N/A'}
- **File:** `flo_{target_branch}`

### What Changed
The content of `flo_{target_branch}` has been replicated from `{self.base_branch}` to maintain consistency across UAT environments.

### Review Checklist
- [ ] Verify the file content matches the source
- [ ] Check for any environment-specific configurations
- [ ] Ensure no sensitive data is included

---
🤖 This PR was automatically generated by the FLO File Sync workflow.
"""
        
        # ============================================================
        # Create the Pull Request using GitHub CLI
        # ============================================================
        # This command creates a PR with:
        #   --base target_branch  : Where the changes will be merged (e.g., uat_na)
        #   --head sync_branch    : Source of changes (e.g., sync-flo-from-uat_emea-to-uat_na-123456)
        #
        # IMPORTANT: The target_branch is PROTECTED by the PR process.
        # Changes cannot be merged until the PR is reviewed and approved.
        # ============================================================
        print(f"🔧 Executing: gh pr create")
        print(f"   --base {target_branch}")
        print(f"   --head {sync_branch}")
        
        # Use GitHub CLI to create the pull request
        # The gh CLI tool is pre-installed on GitHub Actions runners
        returncode, pr_url, error = self.run_command([
            "gh", "pr", "create",
            "--base", target_branch,      # TARGET: Where changes will be merged
            "--head", sync_branch,        # SOURCE: Branch with the changes
            "--title", pr_title,
            "--body", pr_body
        ], check=False)
        
        if returncode != 0:
            print(f"❌ Failed to create PR: {error}")
            return None
        
        print(f"✅ Created PR: {pr_url}")
        
        # Store the PR information for later use
        self.created_prs.append({
            "target_branch": target_branch,
            "sync_branch": sync_branch,
            "pr_url": pr_url
        })
        
        return pr_url
    
    def add_comment_to_original_pr(self) -> bool:
        """
        Add a comment to the original PR with links to all created PRs.
        
        Returns:
            True if comment was added successfully, False otherwise
        """
        if not self.pr_number:
            print("ℹ️  No PR number available, skipping comment")
            return False
        
        if not self.created_prs:
            print("ℹ️  No PRs were created, skipping comment")
            return False
        
        print(f"\n💬 Adding comment to original PR #{self.pr_number}...")
        
        # Build a list of PR links in markdown format
        pr_links = []
        for pr_info in self.created_prs:
            pr_links.append(f"- [{pr_info['target_branch']}]({pr_info['pr_url']})")
        
        pr_links_text = '\n'.join(pr_links)
        
        # Construct the comment body
        comment_body = f"""## 🔄 FLO File Changes Replicated

Changes to `{self.flo_file}` have been automatically replicated to other UAT branches.

### Created Pull Requests:
{pr_links_text}

**Next Steps:**
1. Review each PR to ensure the changes are correct
2. Merge the PRs to synchronize all UAT environments
3. Monitor for any deployment or testing issues

---
🤖 Automated by FLO File Sync workflow | [View workflow run](https://github.com/${{{{GITHUB_REPOSITORY}}}}/actions/runs/${{{{GITHUB_RUN_ID}}}})
"""
        
        # Use GitHub CLI to add the comment
        returncode, _, error = self.run_command([
            "gh", "pr", "comment", self.pr_number,
            "--body", comment_body
        ], check=False)
        
        if returncode != 0:
            print(f"❌ Failed to add comment: {error}")
            return False
        
        print(f"✅ Comment added to PR #{self.pr_number}")
        return True
    
    def run_sync_workflow(self, commit_sha: str) -> int:
        """
        Execute the complete sync workflow.
        
        ============================================================
        WORKFLOW OVERVIEW - NO DIRECT COMMITS TO TARGET BRANCHES!
        ============================================================
        
        This workflow follows a SAFE, PR-based approach:
        
        1. DETECT: Check if flo_{branch_name} was changed in original PR
        
        2. READ: Get the content of the changed file
        
        3. SYNC: For each target branch (e.g., uat_na, uat_apac, uat_latam):
           a. Create a NEW sync branch (e.g., sync-flo-from-uat_emea-to-uat_na-123456)
           b. Commit changes to the NEW sync branch
           c. Push the NEW sync branch to remote
           d. Create PR: sync_branch → target_branch
        
        4. COMMENT: Add links to all created PRs on the original PR
        
        IMPORTANT: Target branches are NEVER modified directly!
        All changes go through the PR review process.
        
        ============================================================
        
        Example Flow:
        - Original PR: feature-branch → uat_emea (changes flo_uat_emea)
        - This creates 3 PRs:
          * sync-flo-from-uat_emea-to-uat_na-123 → uat_na
          * sync-flo-from-uat_emea-to-uat_apac-456 → uat_apac
          * sync-flo-from-uat_emea-to-uat_latam-789 → uat_latam
        - Original PR gets comment with links to all 3 PRs
        
        ============================================================
        
        Args:
            commit_sha: The commit SHA to check for changes
            
        Returns:
            Exit code (0 for success, 1 for failure)
        """
        print("\n" + "="*60)
        print("🚀 Starting FLO File Sync Workflow")
        print("="*60)
        
        # Step 1: Detect if the flo file was changed
        if not self.detect_file_changes(commit_sha):
            print("\n✅ No changes to FLO file detected. Exiting gracefully.")
            return 0
        
        # Step 2: Read the content of the changed flo file
        print(f"\n📖 Reading content from {self.flo_file}...")
        
        # First, make sure we're on the right commit
        self.run_command(["git", "checkout", commit_sha])
        
        file_content = self.get_file_content(self.flo_file)
        if file_content is None:
            print(f"❌ Failed to read {self.flo_file}")
            return 1
        
        # Step 3: Sync to each target branch
        print(f"\n🔄 Syncing to {len(self.target_branches)} target branches...")
        print(f"⚠️  Remember: We create PRs, NOT direct commits!")
        print()
        
        synced_branches = []  # Track which branches actually got PRs created
        
        for target_branch in self.target_branches:
            # Create sync branch and commit changes to it (NOT to target branch!)
            sync_branch = self.sync_to_target_branch(target_branch, file_content)
            
            if sync_branch:
                # Changes were made to sync_branch, now create a PR to target_branch
                print(f"\n📋 Changes ready in {sync_branch}")
                print(f"   Now creating PR: {sync_branch} → {target_branch}")
                
                pr_url = self.create_pull_request(target_branch, sync_branch)
                
                if pr_url:
                    synced_branches.append(target_branch)
                    print(f"✅ PR created successfully: {pr_url}")
            else:
                print(f"⏭️  Skipping {target_branch} - no changes needed (already in sync)")
        
        # Step 4: Add comment to original PR if any PRs were created
        if self.created_prs:
            print(f"\n📊 Summary: Created {len(self.created_prs)} pull request(s)")
            self.add_comment_to_original_pr()
        else:
            print("\nℹ️  No pull requests were created (all branches already in sync)")
        
        print("\n" + "="*60)
        print("✅ FLO File Sync Workflow Completed Successfully")
        print("="*60)
        
        return 0


def main():
    """
    Main entry point for the script.
    
    Reads environment variables set by GitHub Actions and executes the sync workflow.
    
    Expected Environment Variables:
        - BASE_BRANCH: The base branch of the PR (e.g., 'uat_emea')
        - CURRENT_BRANCH: The head/source branch of the PR
        - COMMIT_SHA: The commit SHA to check for changes
        - PR_NUMBER: The pull request number (optional)
    """
    print("="*60)
    print("FLO File Sync Script - Starting")
    print("="*60)
    
    # Read environment variables set by the GitHub Actions workflow
    base_branch = os.getenv("BASE_BRANCH")
    current_branch = os.getenv("CURRENT_BRANCH")
    commit_sha = os.getenv("COMMIT_SHA")
    pr_number = os.getenv("PR_NUMBER")
    
    # Validate that all required environment variables are present
    if not base_branch:
        print("❌ Error: BASE_BRANCH environment variable not set")
        sys.exit(1)
    
    if not current_branch:
        print("❌ Error: CURRENT_BRANCH environment variable not set")
        sys.exit(1)
    
    if not commit_sha:
        print("❌ Error: COMMIT_SHA environment variable not set")
        sys.exit(1)
    
    print(f"\n📋 Configuration:")
    print(f"   Base Branch: {base_branch}")
    print(f"   Current Branch: {current_branch}")
    print(f"   Commit SHA: {commit_sha}")
    print(f"   PR Number: {pr_number or 'N/A'}")
    print()
    
    # Initialize the sync manager with the provided configuration
    sync_manager = FLOFileSyncManager(
        base_branch=base_branch,
        current_branch=current_branch,
        pr_number=pr_number
    )
    
    # Execute the sync workflow
    exit_code = sync_manager.run_sync_workflow(commit_sha)
    
    # Exit with the appropriate code
    sys.exit(exit_code)


if __name__ == "__main__":
    main()