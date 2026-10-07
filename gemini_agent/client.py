                                tool_result = f"Tool error: {exc}"
                        else:
                            args = {}
                            tool_result = f"Tool error: {exc}"

                    if self.goal_state is not None:
                        self.goal_state.add_evidence(str(tool_result))
                        bounded_observation_evidence = (
                            self.goal_state.evidence[-1]
                            if self.goal_state.evidence
                            else str(tool_result)[:512]
                        )
                        observation = observe_goal_progress(
                            self.goal_state.goal,
                            self.goal_state.success_condition,
                            bounded_observation_evidence,
                        )
                        self.goal_state.progress_status = observation.status
                        self.goal_state.progress_reason = observation.reason
                        goal_result = str(tool_result)
                        recovery_match = re.search(
                            r"Recovery result:\s*(.*?)(?=\n(?:Diagnosis|Failure learning|Recovery learning):|$)",
                            goal_result,
                            re.IGNORECASE | re.DOTALL,
                        )
                        recovery_result = recovery_match.group(1).strip() if recovery_match else ""
                        if recovery_result:
                            recovery_result = re.split(
                                r"(?:\\\\n|\\n|\\r?\\n)",
                                recovery_result,
                                maxsplit=1,
                            )[0].strip()
                        if not recovery_result:
                            verified_match = re.search(
                                r"(?:Post-action verification|Verification|Postcondition|Outcome)\s*:\s*VERIFIED\b",
                                goal_result,
                                re.IGNORECASE,
                            )
                            if verified_match:
                                recovery_result = goal_result[verified_match.start():]
                                recovery_result = re.split(
                                    r"(?:\\\\n|\\n|\\r?\\n)",
                                    recovery_result,
                                    maxsplit=1,
                                )[0].strip()
                        recovery_verified = bool(
                            raw_tool_failed
                            and recovery_result
                            and re.search(
                                r"(?:Post-action verification|Verification|Postcondition|Outcome)\s*:\s*VERIFIED\b",
                                recovery_result,
                                re.IGNORECASE,
                            )
                        )
                        # Completion evidence must distinguish a recovered failure from an
                        # unresolved failure. A failed step remains FAILED in the ledger, but its
                        # raw Tool error must not poison later completion verification after verified
                        # recovery. Preserve only the bounded verified recovery evidence for recovered
                        # failed steps.
                        normalized_step_evidence = []
                        for step in self.goal_state.steps:
                            step_evidence = str(step.get("evidence", ""))
                            if step.get("status") == "FAILED":
                                verified_step_match = re.search(
                                    r"(?:Post-action verification|Verification|Postcondition|Outcome)\\s*:\\s*VERIFIED\\b",
                                    step_evidence,
                                    re.IGNORECASE,
                                )
                                if verified_step_match:
                                    recovered_evidence = step_evidence[verified_step_match.start():]
                                    recovered_evidence = re.split(
                                        r"(?:\\\\n|\\n|\\r?\\n)",
                                        recovered_evidence,
                                        maxsplit=1,
                                    )[0].strip()
                                    if recovered_evidence:
                                        normalized_step_evidence.append(recovered_evidence)
                                    continue
                            normalized_step_evidence.append(step_evidence)
                        normalized_step_evidence.append(str(tool_result))
                        completion_evidence = "\n".join(
                            [*normalized_step_evidence, f"Observed tool: {local_name}"]
                        )
                        if recovery_verified:
                            normalized_step_evidence = [
                                evidence
                                for evidence in normalized_step_evidence
                                if evidence != str(tool_result)
                            ]
                            # Recovery reports may contain learning/meta text that repeats the
                            # original goal wording. Only the bounded verified recovery evidence should
                            # contribute to goal completion, otherwise metadata can falsely satisfy a
                            # remaining success-condition clause.
                            completion_evidence = "\n".join(
                                [*normalized_step_evidence, recovery_result, f"Observed recovery for: {local_name}"]
                            )
                        completion = verify_goal_completion(
                            self.goal_state.goal,
                            self.goal_state.success_condition,
                            completion_evidence,
                        )
                        if completion.status == "VERIFIED":