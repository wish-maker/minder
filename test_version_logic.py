#!/usr/bin/env python3
"""
Test version parsing, comparison, and classification against real Docker Hub data.
Run locally BEFORE committing to workflow.
"""

import re
import yaml
import requests
from typing import Dict, List, Tuple, Optional

# ============================================================================
# TAG PARSING
# ============================================================================

def parse_tag(tag: str) -> Tuple[str, str]:
    """Parse tag into (version, suffix)"""
    tag = tag.lstrip('v')
    match = re.match(r'^([0-9]+(?:\.[0-9]+)*)-(.+)$', tag)
    if match:
        return match.group(1), '-' + match.group(2)
    else:
        return tag, ''

def should_skip_tag(tag: str) -> bool:
    """Skip non-version tags"""
    skip_patterns = [
        r'^latest$', r'^dev$', r'^master$',
        r'^sha256-', r'.*-unprivileged$', r'.*-gpu-.*$',
    ]
    for pattern in skip_patterns:
        if re.match(pattern, tag):
            return True
    return False

def parse_version_safe(version_str: str) -> Optional[Tuple]:
    """Parse version string into comparable tuple (handles X.Y.Z, X.Y, X)"""
    parts = version_str.split('.')
    try:
        int_parts = [int(p) for p in parts]
        while len(int_parts) < 3:
            int_parts.append(0)
        return tuple(int_parts[:3])
    except (ValueError, AttributeError):
        return None

def detect_version_scheme(version_str: str) -> str:
    """
    Detect version scheme: 'semver', 'calver', or 'unknown'
    Calver: YYYY.M.D or YYYY.M (e.g., 2026.05.0, 2024.3)
    Semver: X.Y.Z where X < 100 (e.g., 5.26.25, 3.7.0)
    """
    parts = version_str.split('.')
    if len(parts) >= 2:
        try:
            first = int(parts[0])
            # Calver: year >= 2000 or 4-digit year
            if first >= 2000 or (len(parts[0]) == 4 and parts[0].isdigit()):
                return 'calver'
        except ValueError:
            pass
    return 'semver'

def classify_update(current_tag: str, latest_tag: str) -> str:
    """
    Classify update as 'patch', 'minor', 'major', or 'scheme-change'
    Assumes both tags are in same track (same suffix)
    """
    current_ver, current_suffix = parse_tag(current_tag)
    latest_ver, latest_suffix = parse_tag(latest_tag)

    # Detect version scheme change (e.g., semver 5.x → calver 2026.x)
    current_scheme = detect_version_scheme(current_ver)
    latest_scheme = detect_version_scheme(latest_ver)

    if current_scheme != latest_scheme:
        return 'scheme-change'

    current_parsed = parse_version_safe(current_ver)
    latest_parsed = parse_version_safe(latest_ver)

    if not current_parsed or not latest_parsed:
        return 'unknown'

    current_major, current_minor, current_patch = current_parsed
    latest_major, latest_minor, latest_patch = latest_parsed

    if latest_major > current_major:
        return 'major'
    elif latest_minor > current_minor:
        return 'minor'
    elif latest_patch > current_patch:
        return 'patch'
    else:
        return 'unknown'

# ============================================================================
# DOCKER HUB API
# ============================================================================

def fetch_all_tags(repo: str) -> List[str]:
    """Fetch all tags from Docker Hub (paginated)"""
    tags = []
    url = f"https://hub.docker.com/v2/repositories/{repo}/tags?page_size=100"
    page = 0
    while url and page < 5:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            for tag_data in data['results']:
                tag_name = tag_data['name']
                if not should_skip_tag(tag_name):
                    tags.append(tag_name)
            url = data.get('next')
            page += 1
        except Exception as e:
            print(f"    [!] API error: {e}")
            break
    return tags

def get_latest_in_track(current_tag: str, all_tags: List[str]) -> Optional[Tuple[str, str]]:
    """Find highest version in same track as current_tag"""
    current_version, current_suffix = parse_tag(current_tag)

    same_track = [tag for tag in all_tags if parse_tag(tag)[1] == current_suffix]

    versions = []
    for tag in same_track:
        ver, _ = parse_tag(tag)
        parsed = parse_version_safe(ver)
        if parsed is not None:
            versions.append((parsed, tag))

    if not versions:
        return None, "no valid versions in track"

    versions.sort(key=lambda x: x[0], reverse=True)
    highest_version, latest_tag = versions[0]
    return latest_tag, "found"

# ============================================================================
# REGISTRY DETECTION
# ============================================================================

def get_registry(image_ref: str) -> str:
    if image_ref.startswith('ghcr.io/'):
        return 'GHCR'
    elif image_ref.startswith('gcr.io/'):
        return 'GCR'
    elif image_ref.startswith('minder/'):
        return 'LOCAL'
    else:
        return 'DOCKER_HUB'

def normalize_repo(image_name: str) -> str:
    if '/' not in image_name:
        return f'library/{image_name}'
    else:
        return image_name

# ============================================================================
# QUERY SPECIFIC TAGS FOR DEBUGGING
# ============================================================================

def query_grafana_tags():
    """Query grafana tags to verify 13.1 is correct"""
    print("\n[?] VERIFYING GRAFANA TAGS")
    tags = fetch_all_tags('grafana/grafana')

    # Find tags around 11-14 range
    relevant = []
    for tag in tags:
        parsed = parse_version_safe(tag.lstrip('v'))
        if parsed and parsed[0] in [11, 12, 13, 14]:
            relevant.append((parsed, tag))

    relevant.sort(reverse=True)
    print(f"    Grafana tags 11-14 range: {[tag for _, tag in relevant[:15]]}")

def verify_prometheus_exporter_repo():
    """Verify the correct repo for postgres-exporter"""
    print("\n[?] VERIFYING PROMETHEUS EXPORTER REPO")

    # Try different repo names
    repos_to_try = [
        'prometheuscommunity/postgres-exporter',
        'prometheuscommunity/postgres-exporter',  # compose uses this
        'quay.io/prometheuscommunity/postgres-exporter',
        'prometheus/postgres-exporter',
    ]

    for repo in repos_to_try:
        print(f"    Trying: {repo}")
        try:
            if repo.startswith('quay.io'):
                # Skip non-Docker Hub for now
                print(f"      Skipped (non-Docker Hub)")
                continue

            url = f"https://hub.docker.com/v2/repositories/{repo}/tags?page_size=5"
            response = requests.get(url, timeout=5)

            if response.status_code == 200:
                print(f"      [+] FOUND at {repo}")
                data = response.json()
                print(f"      Tags: {[t['name'] for t in data['results'][:5]]}")
                return repo
            elif response.status_code == 404:
                print(f"      [-] Not found (404)")
            else:
                print(f"      [?] Status {response.status_code}")
        except Exception as e:
            print(f"      [X] Error: {e}")

    return None

# ============================================================================
# MAIN CHECK LOGIC
# ============================================================================

def check_updates_from_compose() -> Dict:
    """Read docker-compose.yml and check for updates"""
    with open('docker/compose/docker-compose.yml', 'r', encoding='utf-8') as f:
        compose = yaml.safe_load(f)

    updates = {}
    results = []

    print("=" * 80)
    print("CHECKING ALL IMAGES FOR UPDATES WITH CLASSIFICATION")
    print("=" * 80)

    for service_name, service_config in compose['services'].items():
        if 'image' not in service_config:
            continue

        image = service_config['image']

        if 'build' in service_config:
            print(f"\n[S] SKIP {service_name}: {image} (has build section)")
            results.append((service_name, image, 'SKIP', 'local build'))
            continue

        registry = get_registry(image)
        if registry != 'DOCKER_HUB':
            print(f"\n[S] SKIP {service_name}: {image} ({registry})")
            results.append((service_name, image, 'SKIP', f'{registry}'))
            continue

        if ':' not in image:
            current_tag = 'latest'
            image_name = image
        else:
            image_name, current_tag = image.rsplit(':', 1)

        if current_tag == 'latest':
            print(f"\n[S] SKIP {service_name}: {image} (latest tag)")
            results.append((service_name, image, 'SKIP', 'latest tag'))
            continue

        print(f"\n[?] CHECK {service_name}: {image}")

        try:
            repo = normalize_repo(image_name)
            print(f"    Repo: {repo}")

            all_tags = fetch_all_tags(repo)
            print(f"    Fetched {len(all_tags)} tags")

            latest_tag, reason = get_latest_in_track(current_tag, all_tags)

            if latest_tag is None:
                print(f"    [!] No latest found: {reason}")
                results.append((service_name, image, 'ERROR', reason))
                continue

            if latest_tag != current_tag:
                # Classify the update
                classification = classify_update(current_tag, latest_tag)
                print(f"    [!] UPDATE: {current_tag} -> {latest_tag} [{classification.upper()}]")

                updates[service_name] = {
                    'image': image_name,
                    'current': current_tag,
                    'latest': latest_tag,
                    'registry': registry,
                    'classification': classification
                }
                results.append((service_name, image, 'UPDATE', f'{current_tag}->{latest_tag} [{classification}]'))
            else:
                print(f"    [*] Up to date")
                results.append((service_name, image, 'OK', 'current'))

        except Exception as e:
            print(f"    [X] ERROR: {e}")
            results.append((service_name, image, 'ERROR', str(e)))

    print("\n" + "=" * 80)
    print("SUMMARY BY CLASSIFICATION")
    print("=" * 80)

    # Group updates by classification
    patch_updates = []
    minor_updates = []
    major_updates = []
    scheme_changes = []
    unknown_updates = []

    for service_name, image, status, detail in results:
        if status == 'UPDATE':
            # Extract classification from detail
            match = re.search(r'\[(\w+)\]', detail)
            if match:
                classification = match.group(1)
                item = (service_name, image, detail)
                if classification == 'patch':
                    patch_updates.append(item)
                elif classification == 'minor':
                    minor_updates.append(item)
                elif classification == 'major':
                    major_updates.append(item)
                elif classification == 'scheme-change':
                    scheme_changes.append(item)
                else:
                    unknown_updates.append(item)

    symbol = {'UPDATE': '[!]', 'OK': '[*]', 'SKIP': '[S]', 'ERROR': '[X]'}

    print("\n[PATCH] Safe to update (backwards compatible):")
    for service_name, image, detail in patch_updates:
        print(f"  {symbol['UPDATE']} {service_name:30} {detail}")

    print("\n[MINOR] Safe to update (feature additions):")
    for service_name, image, detail in minor_updates:
        print(f"  {symbol['UPDATE']} {service_name:30} {detail}")

    print("\n[MAJOR] Review carefully (breaking changes possible):")
    for service_name, image, detail in major_updates:
        print(f"  {symbol['UPDATE']} {service_name:30} {detail}")

    if scheme_changes:
        print("\n[SCHEME CHANGE] Version scheme changed (MAJOR risk):")
        for service_name, image, detail in scheme_changes:
            print(f"  {symbol['UPDATE']} {service_name:30} {detail}")

    if unknown_updates:
        print("\n[UNKNOWN] Could not classify:")
        for service_name, image, detail in unknown_updates:
            print(f"  {symbol['UPDATE']} {service_name:30} {detail}")

    print("\n" + "=" * 80)
    print("FULL RESULTS")
    print("=" * 80)

    for service_name, image, status, detail in results:
        symbol = {'UPDATE': '[!]', 'OK': '[*]', 'SKIP': '[S]', 'ERROR': '[X]'}.get(status, '[?]')
        print(f"{symbol} {service_name:30} {status:8} {detail}")

    update_count = sum(1 for _, _, status, _ in results if status == 'UPDATE')
    ok_count = sum(1 for _, _, status, _ in results if status == 'OK')
    skip_count = sum(1 for _, _, status, _ in results if status == 'SKIP')
    error_count = sum(1 for _, _, status, _ in results if status == 'ERROR')

    print(f"\nTotal: {len(results)} | Updates: {update_count} | OK: {ok_count} | Skip: {skip_count} | Error: {error_count}")

    return updates

if __name__ == '__main__':
    # Run verifications first
    query_grafana_tags()
    verify_prometheus_exporter_repo()

    print("\n" + "=" * 80)
    print("MAIN CHECK")
    print("=" * 80)

    updates = check_updates_from_compose()

    print("\n" + "=" * 80)
    print("UPDATES JSON (for workflow)")
    print("=" * 80)

    if updates:
        import json
        print(json.dumps(updates, indent=2))
    else:
        print("{}")
