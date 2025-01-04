#!/usr/bin/env python3

import argparse
import re
import subprocess
from pathlib import Path
from rich.console import Console
from rich.tree import Tree
from rich import print as rprint
from typing import List, Tuple
import pandas as pd

def run_command_for_files(file_paths: List[str | Path], command: str) -> List[Tuple[str, str, str]]:
    """
    Run a shell command for each file in the input list and capture stdout and stderr.
    
    Args:
        file_paths: List of file paths to process
        command: Shell command to run. Use {filepath} as placeholder for the file path
        
    Returns:
        List of tuples containing (filepath, stdout, stderr) for each file
    """
    results = []
    
    for file_path in file_paths:
        file_path = str(file_path)  # Convert Path to string if needed
        try:
            file_path = re.sub(r'[()]', lambda m: f'\\{m.group(0)}', file_path)
            # Replace the placeholder with actu
            formatted_command = f"{command} {file_path}"
            print(f"Running command: `{formatted_command}`")
            # Run the command and capture output
            process = subprocess.Popen(
                formatted_command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True  # Return strings instead of bytes
            )
            
            # Get stdout and stderr
            stdout, stderr = process.communicate()
            
            # Add results to list
            results.append((file_path, stdout.strip(), stderr.strip()))
            
        except Exception as e:
            # If there's any error, capture it in stderr
            results.append((file_path, "", str(e)))
    
    return results

def collect_files(directory: Path, pattern: str | None = None) -> list[Path]:
    """Recursively collect all files in the given directory that match the pattern."""
    files = []
    for item in directory.rglob("*"):
        if item.is_file():
            # If pattern is provided, check if file matches the pattern
            if pattern is None or re.search(pattern, str(item.name)):
                files.append(item)
    return files

def create_file_tree(directory: Path, pattern: str | None = None) -> Tree:
    """Create a rich Tree representation of the files."""
    abs_dir = directory.absolute()
    tree = Tree(f"📁 [bold blue]{abs_dir}[/]")
    if pattern:
        tree.label += f" [yellow](Filter: {pattern})[/]"
    
    files = collect_files(directory, pattern)
    
    for file in sorted(files):
        abs_file = file.absolute()
        # Get relative path for better display
        rel_path = abs_file.relative_to(abs_dir)
        tree.add(f"📄 [green]{rel_path}[/] ([dim]{abs_file}[/])")
    
    return tree

def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape codes from text."""
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\[\d+m')
    return ansi_pattern.sub('', text)

def parse_vale_output(stdout: str, filename: str = None) -> pd.DataFrame:
    """
    Parse Vale linter output and convert to a DataFrame.
    
    Args:
        stdout: String output from Vale command
        filename: Optional filename being processed
        
    Returns:
        DataFrame with columns: filename, line, col, error_type, error_msg, check_name
    """
    # Initialize lists to store the parsed data
    filenames = []
    line_nums = []
    col_nums = []
    error_types = []
    error_msgs = []
    check_names = []
    
    # Split the output into lines and strip ANSI codes
    lines = [strip_ansi_codes(line) for line in stdout.strip().split('\n')]
    
    # Get filename from first line if not provided
    if not filename and lines and lines[0].strip().endswith(('.mdx', '.md')):
        filename = lines[0].strip()
    
    # Skip only the first line if it's just the filename
    start_idx = 1 if len(lines) > 1 and (lines[0].endswith('.mdx') or lines[0].endswith('.md')) else 0
    
    i = start_idx
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines and summary lines
        if not line or line.startswith('✖'):
            i += 1
            continue
        
        try:
            # First try to match the line:col, type and rule
            location_pattern = r'^\s*(\d+):(\d+)\s+(\w+)\s+(.+)$'
            location_match = re.match(location_pattern, line)
            
            if location_match:
                line_num, col_num, error_type, rest = location_match.groups()
                
                # Then split the rest to get message and check_name
                # Split on two or more spaces to handle varying amounts of spacing
                parts = re.split(r'\s{2,}', rest)
                
                if len(parts) >= 2:  # Changed condition to handle cases with multiple spaces
                    msg = ' '.join(parts[:-1])  # Join all parts except the last one
                    check_name = parts[-1]  # Last part is the check name
                    
                    # Initialize full message
                    full_msg = msg.strip()
                    
                    # Look ahead at next lines to get the full message
                    next_idx = i + 1
                    while (next_idx < len(lines) and 
                           lines[next_idx].strip() and 
                           not re.match(r'^\d+:\d+', lines[next_idx]) and
                           not lines[next_idx].startswith('✖')):
                        additional_text = re.sub(r'^\s+', '', lines[next_idx].strip())
                        if additional_text:
                            full_msg += ' ' + additional_text
                        next_idx += 1
                    
                    # Add to our lists
                    filenames.append(filename)
                    line_nums.append(int(line_num))
                    col_nums.append(int(col_num))
                    error_types.append(error_type)
                    error_msgs.append(full_msg.strip())
                    check_names.append(check_name.strip())
                    
                    # Move to the next error
                    i = next_idx
                    continue
            
        except Exception as e:
            # If there's an error parsing, skip this line
            pass
        
        i += 1
    
    # Create DataFrame
    df = pd.DataFrame({
        'filename': filenames,
        'line': line_nums,
        'col': col_nums,
        'error_type': error_types,
        'error_msg': error_msgs,
        'check_name': check_names
    })
    
    return df

def main():
    parser = argparse.ArgumentParser(description="List all files in a directory recursively and optionally run a command on them")
    parser.add_argument("directory", type=str, help="Directory to traverse")
    parser.add_argument("-p", "--pattern", type=str, help="Regex pattern to filter files (e.g. '\\.py$' for Python files)")
    parser.add_argument("-c", "--command", type=str, help="Command to run on each file. Use {filepath} as placeholder for the file path")
    args = parser.parse_args()
    
    directory = Path(args.directory)
    if not directory.exists() or not directory.is_dir():
        rprint(f"[red]Error: {directory} is not a valid directory[/]")
        return
    
    # Collect and display files
    console = Console()
    tree = create_file_tree(directory, args.pattern)
    console.print(tree)
    
    files = collect_files(directory, args.pattern)
    matched_files = len(files)
    total_files = len(list(directory.rglob("*")))
    rprint(f"\n[bold cyan]Files matching pattern: {matched_files} (out of {total_files} total files)[/]")
    
    # If command is provided, run it on all matched files
    if args.command:
        rprint(f"\n[bold yellow]Running command: {args.command}[/]")
        results = run_command_for_files(files, args.command)
        
        # Collect all DataFrames
        all_dfs = []
        
        # Print results
        for filepath, stdout, stderr in results:
            rprint(f"\n[bold green]File: {filepath}[/]")
            if stdout:
                print(stdout)
                # Parse the output into a DataFrame if it's not empty
                if 'warning' in stdout or 'error' in stdout:  # Basic check for Vale output
                    df = parse_vale_output(stdout, str(filepath))
                    if not df.empty:
                        all_dfs.append(df)
            if stderr:
                rprint(f"[red]Error:[/]\n{stderr}")
        
        # Concatenate all DataFrames if we have any
        if all_dfs:
            final_df = pd.concat(all_dfs, ignore_index=True)
            rprint("\n[bold cyan]All Parsed Results:[/]")
            print(final_df.to_string(index=False))
            
            # Create error report DataFrame
            error_report = final_df.groupby(['error_type', 'check_name']).size().reset_index(name='count')
            error_report = error_report.sort_values('count', ascending=False)
            
            rprint("\n[bold cyan]Error Report Summary:[/]")
            print(error_report.to_string(index=False))
            rprint(f"\n[bold cyan]Total issues found: {len(final_df)}[/]")

if __name__ == "__main__":
    main() 