"""
Unified category mapping across brands.

Each brand can define its own prefix→category map. This module provides
a shared taxonomy and helper functions for consistent categorization.
"""

# Shared category taxonomy used across all brands
STANDARD_CATEGORIES = [
    "furniture",
    "playground",
    "outdoor",
    "nature_play",
    "balance",
    "loose_parts",
    "creative",
    "water_play",
    "climbing",
    "early_years",
    "sports",
    "sensory",
    "storage",
    "other",
    "uncategorized",
]

# Subcategory keywords shared across brands
SUBCATEGORY_KEYWORDS = {
    "cabinet": "cabinet",
    "table": "table",
    "chair": "chair",
    "slide": "slide",
    "swing": "swing",
    "tower": "tower",
    "shelf": "shelf",
    "bed": "bed",
    "desk": "desk",
    "fence": "fence",
    "bench": "bench",
    "sand": "sand_play",
    "climb": "climbing",
    "balance": "balance",
    "kitchen": "kitchen",
    "house": "house",
    "play": "play_structure",
}


def classify_category(item_code, category_map):
    """Classify an item code into a category using the given prefix map.

    Args:
        item_code: Product item code string
        category_map: Dict of {prefix: category} for this brand
    Returns:
        Category string
    """
    import pandas as pd
    if not item_code or pd.isna(item_code):
        return "uncategorized"
    code = str(item_code).upper()
    # Sort by prefix length descending so longer prefixes match first
    for prefix, cat in sorted(category_map.items(), key=lambda x: -len(x[0])):
        if code.startswith(prefix):
            return cat
    return "other"


def classify_subcategory(description):
    """Derive subcategory from product description keywords."""
    import pandas as pd
    if not description or pd.isna(description):
        return None
    desc_lower = str(description).lower()
    for keyword, subcat in SUBCATEGORY_KEYWORDS.items():
        if keyword in desc_lower:
            return subcat
    return None
