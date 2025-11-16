from __future__ import annotations

# Common pieces
ToolEnum = {
    "type": "string",
    "enum": [
        "open",
        "type",
        "click",
        "press",
        "waitFor",
        "assertVisible",
        "assertText",
        "assertUrl",
        "custom",
        "doubleClick",
        "rightClick",
        "hover",
        "focus",
        "blur",
        "clear",
        "select",
        "upload",
        "drag",
        "dragAndDrop",
        "scroll",
        "reload",
        "back",
        "forward",
        "newTab",
        "newWindow",
        "switchTab",
        "switchWindow",
        "closeTab",
        "closeWindow",
    ],
}

TargetQuerySchema = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "minLength": 1},
        "css": {"type": "string", "minLength": 1},
        "hints": {
            "type": "object",
            "properties": {
                "role": {"type": "string"},
                "color": {"type": "string"},
                "near": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "scope": {"type": "string"},
    },
    "additionalProperties": False,
    # require at least one of text or css for a valid target
    "anyOf": [
        {"required": ["text"]},
        {"required": ["css"]},
    ],
}

# Per-tool arg schemas (M1 tools only)
Args = {
    "open": {
        "type": "object",
        "properties": {"url": {"type": "string", "minLength": 1}},
        "required": ["url"],
        "additionalProperties": False,
    },
    "type": {
        "type": "object",
        "properties": {
            "target": TargetQuerySchema,
            "text": {"type": "string"},
            "clear": {"type": "boolean"},
        },
        "required": ["target", "text"],
        "additionalProperties": False,
    },
    "click": {
        "type": "object",
        "properties": {"target": TargetQuerySchema},
        "required": ["target"],
        "additionalProperties": False,
    },
    "doubleClick": {
        "type": "object",
        "properties": {"target": TargetQuerySchema},
        "required": ["target"],
        "additionalProperties": False,
    },
    "rightClick": {
        "type": "object",
        "properties": {"target": TargetQuerySchema},
        "required": ["target"],
        "additionalProperties": False,
    },
    "hover": {
        "type": "object",
        "properties": {"target": TargetQuerySchema},
        "required": ["target"],
        "additionalProperties": False,
    },
    "focus": {
        "type": "object",
        "properties": {"target": TargetQuerySchema},
        "required": ["target"],
        "additionalProperties": False,
    },
    "blur": {
        "type": "object",
        "properties": {"target": TargetQuerySchema},
        "required": ["target"],
        "additionalProperties": False,
    },
    "clear": {
        "type": "object",
        "properties": {"target": TargetQuerySchema},
        "required": ["target"],
        "additionalProperties": False,
    },
    "select": {
        "type": "object",
        "properties": {
            "target": TargetQuerySchema,
            "option": {
                "type": "object",
                "properties": {
                    "value": {"type": "string"},
                    "label": {"type": "string"},
                    "index": {"type": "integer", "minimum": 0},
                },
                "minProperties": 1,
                "additionalProperties": False,
                "anyOf": [
                    {"required": ["value"]},
                    {"required": ["label"]},
                    {"required": ["index"]},
                ],
            },
        },
        "required": ["target", "option"],
        "additionalProperties": False,
    },
    "upload": {
        "type": "object",
        "properties": {
            "target": TargetQuerySchema,
            "files": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        },
        "required": ["target", "files"],
        "additionalProperties": False,
    },
    "drag": {
        "type": "object",
        "properties": {
            "target": TargetQuerySchema,
            "dx": {"type": "integer"},
            "dy": {"type": "integer"},
        },
        "required": ["target", "dx", "dy"],
        "additionalProperties": False,
    },
    "dragAndDrop": {
        "type": "object",
        "properties": {
            "target": TargetQuerySchema,
            "to": TargetQuerySchema,
        },
        "required": ["target", "to"],
        "additionalProperties": False,
    },
    "scroll": {
        "type": "object",
        "properties": {
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
            "amount": {"type": "integer"},
        },
        "additionalProperties": False,
        "oneOf": [
            {"required": ["x", "y"]},
            {"required": ["direction", "amount"]},
        ],
    },
    "reload": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "back": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "forward": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "newTab": {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "additionalProperties": False,
    },
    "newWindow": {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "additionalProperties": False,
    },
    "switchTab": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "minimum": 0},
            "urlContains": {"type": "string"},
            "titleContains": {"type": "string"},
        },
        "minProperties": 1,
        "additionalProperties": False,
    },
    "switchWindow": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "minimum": 0},
            "urlContains": {"type": "string"},
            "titleContains": {"type": "string"},
        },
        "minProperties": 1,
        "additionalProperties": False,
    },
    "closeTab": {
        "type": "object",
        "properties": {"index": {"type": "integer", "minimum": 0}},
        "additionalProperties": False,
    },
    "closeWindow": {
        "type": "object",
        "properties": {"index": {"type": "integer", "minimum": 0}},
        "additionalProperties": False,
    },
    "press": {
        "type": "object",
        "properties": {"key": {"type": "string", "minLength": 1}},
        "required": ["key"],
        "additionalProperties": False,
    },
    "waitFor": {
        "type": "object",
        "properties": {
            "target": TargetQuerySchema,
            "url": {"type": "string"},
            "state": {"type": "string", "enum": ["visible", "hidden", "networkidle"]},
            "timeout": {"type": "integer", "minimum": 0},
        },
        "minProperties": 1,
        "additionalProperties": False,
        # at least one of (target|url|state)
        "anyOf": [
            {"required": ["target"]},
            {"required": ["url"]},
            {"required": ["state"]},
        ],
    },
    "assertVisible": {
        "type": "object",
        "properties": {"target": TargetQuerySchema},
        "required": ["target"],
        "additionalProperties": False,
    },
    "assertText": {
        "type": "object",
        "properties": {
            "target": TargetQuerySchema,
            "expected": {"type": "string"},
            "match": {"type": "string", "enum": ["equals", "contains", "regex"]},
        },
        "required": ["target", "expected"],
        "additionalProperties": False,
    },
    "assertUrl": {
        "type": "object",
        "properties": {
            "expected": {"type": "string"},
            "match": {"type": "string", "enum": ["equals", "contains", "regex"]},
        },
        "required": ["expected"],
        "additionalProperties": False,
    },
    "custom": {
        "type": "object",
        "properties": {"script": {"type": "string"}},
        "required": ["script"],
        "additionalProperties": False,
    },
}

ToolCallSchema = {
    "type": "object",
    "properties": {
        "tool": ToolEnum,
        "args": {"type": "object"},  # tightened by oneOf below
        "meta": {"type": "object"},
    },
    "required": ["tool", "args"],
    "additionalProperties": False,
    "allOf": [
        {
            "oneOf": [
                {"properties": {"tool": {"const": name}, "args": Args[name]}}
                for name in Args.keys()
            ]
        }
    ],
}

PlanSchema = {
    "$id": "https://kaizen/schemas/plan.json",
    "type": "array",
    "items": ToolCallSchema,
    "minItems": 1,
}
