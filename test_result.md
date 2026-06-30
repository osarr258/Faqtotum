#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================
## user_problem_statement: "Construire le moteur d'intelligence backend de ProConnect (architecte IA): moteur de matching pondéré multi-critères avec explications IA en français, mode urgence (broadcast multi-pros, premier qui accepte gagne), architecture de synchronisation calendrier (MOCKÉE), et modèles future-ready (Home Passport, Factures, Garanties). Design intact (dark/or champagne)."

## backend:
##   - task: "Moteur de matching IA pondéré + explications FR (/missions)"
##     implemented: true
##     working: true
##     file: "backend/services/matching.py, backend/server.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         -working: true
##         -agent: "main"
##         -comment: "Branché matching.rank() dans POST /missions. top_matches incluent match_score, match_label (confidence_label) et match_reasons (FR). _set_candidate (refuse->next) re-score le candidat. Vérifié via curl: raisons FR correctes, scores variés."
##   - task: "Mode urgence: broadcast multi-pros + premier qui accepte gagne"
##     implemented: true
##     working: true
##     file: "backend/server.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         -working: true
##         -agent: "main"
##         -comment: "urgency=urgence => mode emergency, status searching, notified_pros (top 5). POST /missions/{id}/pro_accept: premier gagne (en_route), 2e renvoie 409. Vérifié via curl."
##   - task: "Architecture synchronisation calendrier (MOCKÉE)"
##     implemented: true
##     working: true
##     file: "backend/services/calendar_sync.py, backend/server.py"
##     stuck_count: 0
##     priority: "medium"
##     needs_retesting: true
##     status_history:
##         -working: true
##         -agent: "main"
##         -comment: "GET /artisans/{id}/availability (créneaux générés, busy depuis bookings), POST /artisans/me/calendar/connect (mock google/outlook/apple). Vérifié via curl."
##   - task: "Modèles future-ready: Home Passport, Factures, Garanties"
##     implemented: true
##     working: true
##     file: "backend/server.py"
##     stuck_count: 0
##     priority: "medium"
##     needs_retesting: true
##     status_history:
##         -working: true
##         -agent: "main"
##         -comment: "complete_mission crée facture + garantie 12 mois + entrée maintenance_history. GET /home-passport, POST /home-passport/equipment, GET /invoices/mine, GET /guarantees/mine. Vérifié via curl."

## frontend:
##   - task: "Écran matching: affichage raisons IA + label de correspondance"
##     implemented: true
##     working: "NA"
##     file: "frontend/app/matching/[id].tsx"
##     stuck_count: 0
##     priority: "medium"
##     needs_retesting: true
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "Ajout section 'Pourquoi l'IA le recommande' (match_reasons) + tag match_label sur cartes non-top. Lint OK. Design inchangé."

## metadata:
##   created_by: "main_agent"
##   version: "2.0"
##   test_sequence: 1
##   run_ui: false

## test_plan:
##   current_focus:
##     - "Moteur de matching IA pondéré + explications FR (/missions)"
##     - "Mode urgence: broadcast multi-pros + premier qui accepte gagne"
##     - "Modèles future-ready: Home Passport, Factures, Garanties"
##   stuck_tasks: []
##   test_all: false
##   test_priority: "high_first"

## agent_communication:
##     -agent: "main"
##     -message: "Couche d'intelligence backend implémentée. Tester en priorité backend: POST /missions (standard + urgence) renvoie top_matches avec match_score/match_label/match_reasons FR; flux refuse/confirm; POST /missions/{id}/pro_accept (premier gagne, 409 sinon); GET /artisans/{id}/availability; POST /artisans/me/calendar/connect; complete_mission -> invoice+guarantee+passport; GET /home-passport, /invoices/mine, /guarantees/mine. Identifiants dans /app/memory/test_credentials.md."
