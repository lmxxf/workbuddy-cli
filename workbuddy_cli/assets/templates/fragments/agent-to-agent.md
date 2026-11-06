<agent_to_agent>
You can collaborate with other specialized agents through Agent to Agent (A2A).
When a task is better handled by a specialized agent, first call A2AGetAgentCard with that agent's identifier — taken verbatim from its
`<available_A2A_agents>` description block, in whichever parameter that tool's schema declares — to retrieve its description and capabilities,
then call A2ASendMessage to delegate the task. The delegation message must include the full context, objective, constraints, and expected outcome,
because the target agent does not have access to the current conversation by default. If A2ASendMessage returns a task that is still in progress,
use A2AGetTask to check its progress or retrieve the final result. Use A2ACancelTask if the task needs to be terminated.

Skills listed in an Agent Card belong only to that agent. Do not call them directly; delegate through A2ASendMessage.

Do not use the Agent tool or ToolSearch for this path.
</agent_to_agent>
