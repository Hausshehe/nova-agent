                {"role": "user", "content": request_text},
            ]

        declarations = self._relevant_tool_declarations(contents)
        if requested_tool:
            declarations = [
                d for d in self.tool_declarations if d["name"] == requested_tool
            ]
        if strategy_candidates and selected_strategy:
            strategy_seed_tool = (
                "record_verified_experience_tool"
                if re.search(
                    r"\bfirst\s+record\s+(?:a\s+)?verified\s+experience\b",
                    request_text,
                    re.IGNORECASE,
                )
                else ""
            )
            # Compound workflows with an explicit seed are deterministic at the
            # boundary: persist the seed locally, then give the provider only the
            # already-selected strategy. This avoids relying on provider-specific
            # "required" tool-choice semantics while keeping selection and execution
            # authoritative.
            if strategy_seed_tool:
                seed_request_match = re.search(
                    r'(?:for|request)\s+(?:experience\s+)?["\']([^"\']+)["\']\s+(?:using|with)\s+(?:strategy\s+)?',
                    request_text,
                    re.IGNORECASE,
                )
                seed_strategy_match = re.search(
                    r'(?:strategy|candidate)\s*(?::|=|\s)\s*([^\s,;]+)',
                    request_text,
                    re.IGNORECASE,
                )
                seed_verification_match = re.search(
                    r'(?:verification|evidence)\s*(?::|=)?\s*(?:"([^"]+)"|\'([^\']+)\'|(.+?))(?=\s+Then\s+|\s+Do not|\s+Report|$)',
                    request_text,
                    re.IGNORECASE | re.DOTALL,
                )
                if seed_request_match and seed_strategy_match and seed_verification_match:
                    seed_args = {
                        "request": seed_request_match.group(1).strip(),
                        "strategy": seed_strategy_match.group(1).strip().rstrip("."),
                        "verification": next(
                            group.strip()
                            for group in seed_verification_match.groups()
                            if group
                        ),
                        "domain": "general",
                    }
                    seed_result = str(
                        self.tool_handlers["record_verified_experience_tool"](**seed_args)
                    )
                    self.last_tool_calls.append({
                        "name": "record_verified_experience_tool",
                        "args": seed_args,
                        "result": seed_result,
                    })
                strategy_seed_tool = ""
            declarations = [
                d for d in self.tool_declarations
                if d["name"] == selected_strategy
            ]

        tools = [{
            "type": "function",
            "function": {
                "name": self._CLOUD_TOOL_NAMES.get(d["name"], d["name"]),
                "description": d["description"],
                "parameters": self._schema(d["parameters"]),
            },
        } for d in declarations]

        payload = {
            "model": self.cloudflare_model,
            "messages": messages,
            "max_completion_tokens": 2048,
            "tools": tools,
        }
        if requested_tool == "apply_capability_extension":
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": "apply_capability_extension"},
            }
        elif strategy_candidates and selected_strategy:
            selected_cloud_name = self._CLOUD_TOOL_NAMES.get(selected_strategy, selected_strategy)
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": selected_cloud_name},
            }
        elif requested_tool:
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": self._CLOUD_TOOL_NAMES.get(requested_tool, requested_tool)},
            }
        elif self._requires_local_tool(contents):
            payload["tool_choice"] = "required"

        url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self.cloudflare_account_id}/ai/v1/chat/completions"
        )
