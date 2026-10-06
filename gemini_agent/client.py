                    try:
                        args = self._parse_tool_arguments(function.get("arguments", "{}"))
                        if local_name == "apply_capability_extension":
                            args = self._fill_extension_request(args, request_text)
                            if str(args.get("implementation_kind", "")).strip().lower() == "android_mechanism":
                                target = str(args.get("implementation_target", "")).strip()
                                target = re.sub(r"^(intent|executable|service|ui-text|ui):\s+", r"\1:", target, flags=re.IGNORECASE)
                                extracted = self._extract_mechanism(target)
                                if extracted:
                                    args["implementation_target"] = extracted
                        tool_result = handler(**args)
                    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                        args = {}
                        tool_result = f"Tool error: {exc}"

                    trace = {"name": local_name, "args": args, "result": tool_result}
                    if "expression" in args:
                        trace["expression"] = str(args["expression"])
                    self.last_tool_calls.append(trace)

                    payload["messages"].append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "content": str(tool_result),
                    })

                    # Self-extension is transactional and must not enter an
                    # unbounded repair conversation with the model. One model
                    # proposal, one local transaction, then return the result.
                    if requested_tool == "apply_capability_extension":
                        return str(tool_result)

                    if requested_tool == "apply_capability_extension" and not str(tool_result).startswith("Extension status: source edit applied and transaction committed."):
                        payload["messages"].append({
                            "role": "user",
                            "content": (
                                "Previous extension attempt failed: "
                                + str(tool_result)
                                + ". Inspect the supplied repository context and call "
                                "apply_capability_extension again with a corrected existing "
                                "path and exact old_text."
                            ),
                        })

                # An explicitly requested local capability is a terminal action for
                # this turn. Return its result after one execution instead of asking the
                # provider to rediscover and call the same capability repeatedly. This also
                # covers capabilities created by self-extension, so generated tools do not
                # need to be hard-coded into the client.
                if requested_tool and loop_index == 0:
                    return str(tool_result)

                # Tool execution is Nova's responsibility. For an explicit
                # single-tool request, synthesize locally after one execution.