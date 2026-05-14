import platform


def get_architecture() -> str:
    arch = platform.machine()

    if arch in ("x86_64", "AMD64"):
        return "amd64"
    elif arch in ("aarch64", "arm64"):
        return "arm64"
    elif arch in ("arm", "armv7l", "armv8l"):
        return "arm"
    elif arch in ("armhf", "armv7l"):
        return "armhf"
    elif arch in ("i386", "i686"):
        return "i386"
    else:
        return "unknown"
