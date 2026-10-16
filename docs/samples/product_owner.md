# Product Owner sample

- Idea: A simple to-do app
- Mode: mock (canned output)

## Vision
Deliver a simple, usable version of: A simple to-do app

## Epic: Core features
The minimum features needed for a first working version.

### Create an item (priority 1, 3 points)
As a user, I want to create a new item, so that I can start tracking my work.

- Given the app is open When I submit a title Then a new item appears in the list
- Given the app is open When I submit an empty title Then I see a validation error

### Complete an item (priority 2, 2 points)
As a user, I want to mark an item as done, so that I can see what is left to do.

- Given an open item When I mark it done Then it is shown as completed

