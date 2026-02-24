from app.ai.product_router import route_prompt


def test_route_prompt_detects_notice_action():
    routed = route_prompt("create notice title: PTM body: Parent meeting audience: parent")
    assert routed["kind"] == "action"
    assert routed["action_type"] == "create_notice"
    assert routed["payload"]["audience"] == "parent"


def test_route_prompt_detects_fees_intent():
    routed = route_prompt("What are my current fee dues?")
    assert routed["kind"] == "query"
    assert routed["intent"] == "fees"


def test_route_prompt_detects_help_intent():
    routed = route_prompt("What can you do for me?")
    assert routed["kind"] == "query"
    assert routed["intent"] == "help"
