# Onboarding Employees Task

Implement a clean, robust multi-step "Employee Onboarding" 
workflow triggered when an employee is imported or activated, which touches 
at least three distinct operational steps (e.g., local database registration, 
simulated IT provisioning, and simulated access/security assignment). 
If any step in the sequence fails, ensure the workflow executes appropriate 
corrective or rollback logic so the system never leaves data in a partially applied 
state.


## Server start
```bash
docker compose up --build -d
```
Navigate to [Swagger doc](http://localhost:8080/docs).