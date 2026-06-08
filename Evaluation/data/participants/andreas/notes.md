# Observation Notes
- User experience: The participant suggest to show some programs before searching in the "search" tab.
- User experience/feature: The participant tried to drag the nodes in the program tree around to reorder them - this is not possible in the current implementation.
- User experience: The participant mentioned that it is hard to visually distinguish the button that adds the program as context in the chat and the actual added context from each other.
- User experience/feature: The participant tried right-clicking a program tree node to add it to the chat as context.
- Bug: The participant experimented with multi cursor in the program editor and tried to press add as program context. This resulted in only the first selected section was added as context.
- User experience: The participant forgot to add the program as context several times expecting the AI to know which program is currently open.
- User experience: The participant searched directly after the programs name (Program1), expecting it to be the top result, but it was not.
- User experience: Thought they forgot to add context as it was not shown under their message, later found it under the chat answer.
- Bug: In the chat input, newlines are not part of the message being sent - this resulted in the assistant not being able to distinguish multiple choice answers.
- Feature: The participant needed a clear AI context button in the frontend.
- Behavior observation: Used ctrl + F to search in the program editor frequently.
- Got frustrated that the AI used too much previous message context to answer a question and thus did not answer the current query.
- Mentioned that when importing a .urpx program, PolyScope might not generate the updated URScript, but used the already generated in the program, which means it could execute the old program. Thus, we would need to force PolyScope to re-generate the URScipt from the new .urpx file.
- URStudio - Task #2: Program Modification - step 3.
    - After 3:20 - When choosing the second waypoint for the first move node, the first waypoint disappears.
    - Final time: 6:54 sec - Used a new approach: Created the waypoints as variables and used those instead of directly defining the waypoints in the move node.


# Use of AI assistant
Did the participant use the AI features for the tasks?

## Task #1: Program Comprehension
- [ ] Identify the key actions used in the robotic program.
- [ ] Write the sequence of actions in the order performed by the robot in the program.
- [x] Write the sequence of waypoints in the order they are reached by the robot in the program.
    - 2x wrong AI answers - newline is missing after sending the chat message, the AI could not distinguish the four options provided.
- [ ] Does the program use any URCap?
- [ ] Which gripper does the program use?
- [x] Which of the following overall applications best match the program.

### Task #2: Program Modification
- [ ] 1.
- [ ] 2.
- [ ] 3.
- [ ] 4.
- [x] 5.
    - The AI retrieved documentation, but the answer described how to do it in the UR interface, and was thus not relevant to the implemented system.