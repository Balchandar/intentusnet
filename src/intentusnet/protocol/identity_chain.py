from typing import List


def extend_identity_chain(chain: List[str], new_id: str) -> List[str]:
    return list(chain) + [new_id]
