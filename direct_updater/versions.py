"""SemVer comparison with common release prefixes and two-part tags."""

import re
from functools import total_ordering

_PATTERN = re.compile(
    r"^(?:plugin-)?[vV]?(0|[1-9]\d*)\.(0|[1-9]\d*)(?:\.(0|[1-9]\d*))?"
    r"(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$"
)


@total_ordering
class Version:
    def __init__(self, value):
        match = _PATTERN.fullmatch(str(value).strip())
        if not match:
            raise ValueError("Version is not valid semantic versioning")
        self.core = (int(match[1]), int(match[2]), int(match[3] or 0))
        self.pre = tuple(match[4].split(".")) if match[4] else ()
        for part in self.pre:
            if not part or (part.isdigit() and len(part) > 1 and part[0] == "0"):
                raise ValueError("Invalid prerelease identifier")
        if match[5] and any(not part for part in match[5].split(".")):
            raise ValueError("Invalid build identifier")
        self.text = ".".join(map(str, self.core))
        if self.pre:
            self.text += "-" + ".".join(self.pre)

    def __eq__(self, other):
        return (self.core, self.pre) == (other.core, other.pre)

    def __lt__(self, other):
        if self.core != other.core:
            return self.core < other.core
        if not self.pre or not other.pre:
            return bool(self.pre) and not other.pre
        for left, right in zip(self.pre, other.pre):
            if left == right:
                continue
            if left.isdigit() and right.isdigit():
                return int(left) < int(right)
            if left.isdigit() != right.isdigit():
                return left.isdigit()
            return left < right
        return len(self.pre) < len(other.pre)
