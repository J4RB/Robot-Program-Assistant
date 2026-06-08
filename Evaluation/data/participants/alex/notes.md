# Observation Notes
- Missing feature: stop button for chat
- User experience: When changing the .urpx file directly the participant noted that blend radius when enabling blend is missing.
- Bug: Program tree disappeared, and an error message was shown in its place - cause unknown.
- Bug: The program in the editor is not saved when moving to another tab e.g. search and back again.
- User experience: The participant expected the answers to refer to line numbers in the code.
- Bug: It is possible to press clear chat history while the assistant is working, causing weird behavior.


# Use of AI assistant
Did the participant use the AI features for the tasks?

## Task #1: Program Comprehension
- [ ] Identify the key actions used in the robotic program.
- [ ] Write the sequence of actions in the order performed by the robot in the program.
- [ ] Write the sequence of waypoints in the order they are reached by the robot in the program.
- [ ] Does the program use any URCap?
- [ ] Which gripper does the program use?
- [ ] Which of the following overall applications best match the program.

### Task #2: Program Modification
- [x] 1.
    - The answer was usefull.
- [x] 2.
    - Is action_name correct way to write moveL or moveJ or did the assistant hallucinate (It only retrieved program snippets - none of them contains it.)
- [x] 3.
    - The answer is based on the UR interface, and thus not relevant to the current system implementation.
- [x] 4.
    - The answer is partially wrong and misleading.
    - Blend radius is mentioned but never show, participant ask the assistant about it, the assistant gives a different variable name, participant is not sure which to use.
- [x] 5.
    - The assistant gave a response relevant to the previous query - the memory and conversation history is too important for the generation.
    - The answer says how to do it in the UR interface, and is thus not relevant to the current system implementation.
