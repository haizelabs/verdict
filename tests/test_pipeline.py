"""
def test_broadcast_input():
    block = Block()
    block >> (a := Unit())
    block >> (b := Unit())

    assert a in (leaf_blocks := block._find_leaf_tasks()) and b in leaf_blocks
    assert a in (root_blocks := block._find_root_tasks()) and b in root_blocks
"""
