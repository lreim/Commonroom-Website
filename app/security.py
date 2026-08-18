def is_safe_local_redirect_target(target):
    if not target or not target.startswith("/"):
        return False
    if target.startswith("//"):
        return False
    if "\\" in target:
        return False
    return True
