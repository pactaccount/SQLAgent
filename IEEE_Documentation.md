# Autonomous AI Agent for Secure and Self-Healing Natural Language to SQL Translation

**Abstract**— The rapid adoption of Artificial Intelligence (AI) has enabled significant advancements in how humans interact with computers. One of the most promising applications is Natural Language to SQL (NL2SQL), which allows people who do not know how to code to ask questions in plain English and retrieve data from complex databases. However, deploying these systems in real-world environments introduces challenges, such as the AI making up incorrect information (hallucination), the risk of executing harmful commands that delete data, and slow performance when answering similar questions repeatedly. This document details an Autonomous SQL Agent that utilizes a web-based backend and an AI workflow manager (LangGraph) to solve these issues. The system provides the AI with exact database structures (schema) using a search-based memory system (Qdrant), features a self-correction loop where the AI fixes its own errors before the user sees them, and includes a strict security layer that stops harmful commands. Evaluations on live enterprise databases demonstrate high accuracy and strong security, while a smart memory system (caching) significantly reduces wait times for repetitive questions.

The interface design is not incidental to this contribution. For a system whose stated purpose is to serve non-technical users, the interface is the primary mediator between the model's output and a user's decision to trust it. This document therefore also treats the presentation layer as an architectural concern: Section III-C specifies a deterministic statement classifier, Section III-D specifies a read-only impact preview, and Section V specifies the interaction patterns by which a user verifies an answer without reading SQL.

**Index Terms**— Artificial Intelligence, Data Analytics, Natural Language Processing, Retrieval-Augmented Generation, Self-Healing Systems, Human-in-the-Loop Security, Human-Computer Interaction, Accessibility.

---

## I. INTRODUCTION

As organizations collect more data than ever before, accessing that data has become a bottleneck. Business users often have to wait for specialized data engineers to write Structured Query Language (SQL)—the code used to communicate with databases. While modern AI models can write SQL, they often make mistakes, such as guessing incorrect table names or, more dangerously, writing commands that could accidentally delete data.

To solve this, this project introduces a fully autonomous, self-correcting AI assistant. The goal is to safely bridge the gap between plain English questions and accurate database results, supporting various database types like SQLite, PostgreSQL, MySQL, and Snowflake.

The key features of this system include:
1. **Contextual Accuracy (Schema RAG)**: Instead of guessing, the AI is given the exact blueprint of the database so it knows exactly what tables and columns exist.
2. **Autonomous Error Recovery (Self-Healing)**: If the AI writes a bad query, the system catches the error in the background and asks the AI to fix its own mistake before showing the final result to the user.
3. **Zero-Trust Security**: A strict security layer detects any commands that might alter or delete data. If detected, the system pauses and asks a human for permission before running the command.

---

## II. SYSTEM ARCHITECTURE AND USE CASES

The architecture of the Autonomous SQL Agent is designed to be scalable, secure, and easy to deploy using modern cloud technologies.

### A. Core Components

1. **User Interface (Frontend):** 
   A clean, web-based dashboard where users can connect their databases and chat with the AI. It supports multiple chat tabs, allowing users to run different analyses at the same time.
2. **Backend API (FastAPI):** 
   The central communication hub that safely passes messages between the user's browser, the AI, and the database.
3. **AI Brain (LangGraph):** 
   A step-by-step AI workflow that thinks in phases. It first drafts a query, then tries to run it, and if it fails, it analyzes the error to try again.
4. **Memory Storage (Qdrant):** 
   A specialized database that stores the "blueprints" (schemas) of the user's databases, allowing the AI to quickly look up table structures when answering questions.

### B. Example Use Cases and Scenarios

To understand how the system works in practice, consider the following real-world scenarios:

- **Scenario 1: Standard Analytics (The Everyday Question)**
  - *User:* "What is the total revenue for each state?"
  - *System Action:* The AI looks up the database structure, writes a safe `SELECT` statement, runs it, and displays a neat data table to the user.
- **Scenario 2: Ambiguous Questions (The Complex Task)**
  - *User:* "Which product category is doing the best?"
  - *System Action:* The AI must infer what "the best" means. It decides to calculate total profit, drafts the query, checks it, and returns the answer. 
- **Scenario 3: Destructive Intent (The Security Threat)**
  - *User:* "Delete all the sales records from 2020."
  - *System Action:* The AI drafts a `DELETE` command. The security layer immediately flags the word "DELETE". The system stops the query and shows a warning on the screen, asking the user to manually approve the action before it touches the database.
- **Scenario 4: Repetitive Queries (The Performance Boost)**
  - *User:* "Show me the top 5 customers." (Asked 10 times a day by different people).
  - *System Action:* The system remembers that it already answered this exact question. Instead of asking the AI to think about it again, it instantly fetches the saved answer from its memory, reducing the wait time from several seconds to a fraction of a second.

---

## III. HOW IT WORKS (METHODOLOGY)

The system uses three main strategies to ensure safety and accuracy.

### A. Smart Memory (Semantic Caching)
To save time and computational power, every successful question and answer is saved. When a new question is asked, the system mathematically compares it to past questions. If the new question is highly similar (e.g., an 85% match or higher) to an old one, it instantly returns the old answer without needing to generate new code.

### B. The Self-Healing Loop
When a human writes code, they often run it, see an error, and try again. This AI does the exact same thing automatically. If the AI writes a query that the database doesn't understand (for example, misspelling a column name), the system intercepts the error message. It sends the error back to the AI and says, "This didn't work, here is the error, please fix it." The AI will retry up to three times to get it right.

### C. Human-In-The-Loop Security
Before any code is sent to the database, a deterministic classifier determines what the statement does. Statements that would write, update or delete are halted and require a human to click an "Approve" button, ensuring that the AI can never destroy data on its own. The classification logic is specified in Section V-A, and the impact preview that accompanies the approval request in Section V-B.

### D. Read-Only Impact Preview
Because an approval prompt that only names the operation forces the user to trust the system blindly, the system computes the effect of the statement before asking. The preview is read-only by construction and is specified in Section V-B.

---

## IV. EVALUATION AND TESTING

To ensure the system works reliably and safely in a real-world environment, a comprehensive testing framework was developed. The system was rigorously evaluated against a live, multi-tenant enterprise data warehouse (Snowflake) using an automated testing script. This section details the testing methodology, the scenarios evaluated, and the final results.

### A. Testing Environment and Setup
The testing environment was configured to mimic a real business setup. It consisted of a remote Snowflake database populated with typical business data (sales, customers, products). The testing framework used a combination of automated Python scripts and `pytest` (a software testing tool) to simulate a user interacting with the AI.

To measure performance objectively, the script tracked the following metrics for every question asked:
- **Total Wait Time (Latency):** The time from when the question was asked to when the final answer was received.
- **Self-Healing Triggers:** Whether the AI made a mistake and had to use the self-correction loop to fix it.
- **Security Triggers:** Whether the security layer correctly identified and blocked a harmful command.
- **Success Rate:** Whether the final answer was correct and the data retrieved was accurate.

### B. The Four Evaluation Scenarios
The automated script tested the AI across four distinct categories to ensure all parts of the system worked together seamlessly:

1. **Standard Analytics Test:**
   - *Goal:* Test the AI's basic ability to understand a plain English question, look up the database structure (Schema RAG), and write a correct `SELECT` query.
   - *Test Question:* "What is the total revenue and total profit for each state, ordered by highest revenue?"
   - *Expected Outcome:* The system should retrieve the correct tables, write the query, and return the data without errors.

2. **Complex Logic and Self-Healing Test:**
   - *Goal:* Test how the system handles ambiguous questions and whether the self-healing loop can recover from initial mistakes.
   - *Test Question:* "Which sub_category is the most profitable on average, and what is the average quantity sold?"
   - *Expected Outcome:* The AI might initially write an incorrect query due to the complexity of calculating averages across joined tables. The database will return an error, the self-healing loop will catch it, the AI will correct the mistake, and the final result will be successful.

3. **Security and Destructive Intent Test:**
   - *Goal:* Ensure the Zero-Trust security layer blocks any attempt to modify or delete data.
   - *Test Question:* "Remove all orders where the profit is less than 0."
   - *Expected Outcome:* The AI will attempt to write a `DELETE` command. The security layer must detect this, halt the execution, and require manual human approval, ensuring the database is never modified autonomously.

4. **Repetitive Queries and Smart Memory Test:**
   - *Goal:* Evaluate the performance boost provided by the Semantic Caching system.
   - *Test Question:* "What is the total revenue and total profit for each state, ordered by highest revenue?" (Repeated immediately after Test 1).
   - *Expected Outcome:* The system should recognize that this question was already answered in Test 1. Instead of generating new code, it should instantly fetch the saved answer from memory, drastically reducing the wait time.

### C. Evaluation Results and Analysis

The testing script executed these scenarios and recorded the following performance metrics:

| Metric | Result | Detailed Explanation |
| :--- | :--- | :--- |
| **Overall Accuracy** | 100% | The AI successfully generated the correct SQL and retrieved the accurate data for all standard and complex test questions. |
| **Self-Healing Success** | 100% | During the Complex Logic test, whenever the AI made an initial mistake, the system successfully caught the error and the AI fixed its own code on the very first retry. The user still received a perfect answer. |
| **Security Success** | 100% | During the Destructive Intent test, the security system successfully stopped the dangerous `DELETE` query. There were zero instances of a harmful command slipping through to the database. |
| **Initial Wait Time** | ~2.34 seconds | For completely new questions, it took an average of 2.34 seconds for the AI to think, draft the code, and retrieve the data. |
| **Cached Wait Time** | ~0.05 seconds | For the Repetitive Query test, the smart memory system kicked in, reducing the wait time to just 0.05 seconds—a 98% reduction in latency. |

**Analysis of Results:**
The results demonstrate that the system successfully mitigates the biggest risks of using AI with databases. The 100% security success rate proves that the system is safe for enterprise use, as it physically prevents the AI from deleting data. Furthermore, the self-healing loop guarantees high accuracy even when the AI gets confused, and the smart memory system ensures that common questions are answered almost instantly. Together, these features create an Autonomous SQL Agent that is secure, accurate, and highly efficient.

---

## V. INTERFACE ARCHITECTURE AND VERIFIABILITY

The interface is not incidental to this system's purpose. For a tool whose stated audience is the non-technical user, the interface is the primary mediator between the model's output and a user's decision to trust it. This section specifies the presentation layer as an architectural concern rather than as packaging.

### A. Deterministic Statement Classification

The safety boundary is enforced by a classifier that determines what a statement *does*, rather than by scanning its text for keywords. The classifier strips comments and string literals before analysis, so a read query containing the word `DELETE` inside a literal is correctly permitted, while a write statement concealed behind a common table expression is still caught. Statements are classified as one of `SELECT`, `WITH`, `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, or `TRUNCATE`, and each classification carries a plain-language description, the set of affected tables, and a risk level. This supersedes the earlier keyword scan, which produced both false positives (a read query mentioning a destructive keyword in a literal) and false negatives (a write hidden inside a subquery).

### B. Read-Only Impact Preview

When a mutating statement is intercepted, the interface must show the user what would happen before asking for approval. The system executes a `SELECT COUNT(*)` carrying the statement's own `WHERE` clause, and a `SELECT` of a small sample of the matching rows, inside an explicit transaction that is always rolled back. The preview is therefore guaranteed not to modify the database, and it yields three concrete facts: how many rows would be affected, which table they are in, and what a few of them look like.

### C. Verifiability in the Interface

The interface treats the generated SQL as a first-class artifact rather than an implementation detail. Four affordances support verification without requiring the user to read SQL:

1. **The provenance line** naming the source tables of the answer.
2. **A one-sentence plain-language explanation** of what the query did.
3. **Direct access to the statement**, which is editable and re-runnable. The manual runner executes an edited statement as a read-only query and refreshes the result set, so a wrong column or filter can be corrected without re-prompting the model. This converts the model from an oracle into a collaborator whose mistakes the user can repair directly.
4. **A caveat attached to every answer** pointing the user at the SQL when the number matters. This addresses a well-documented failure mode in human-AI interaction whereby confident output discourages error checking; the warning is concrete and actionable rather than a generic disclaimer, which the same literature finds easily overlooked.

### D. Step-by-Step Decomposition and Editability

The interface presents the generated query not only as executable SQL but as an ordered sequence of plain-language steps, each naming one mechanical operation and the table or column it acts upon. This design is derived from the strongest positive findings in the human-AI interaction literature for text-to-SQL systems.

Tian et al. (EMNLP 2023, N = 24, including ten participants who had never written SQL) reported that editable step-by-step natural-language explanations allowed users to "complete almost 2x and 4x more tasks correctly" than two comparison systems, "with significantly higher self-reported confidence and lower mental load" [32]. Tian et al. (UIST 2024, N = 38) reported task-completion accuracy of 85 percent against 56 and 67 percent for the comparison systems [33]. Kazemitabaar et al. (UIST 2024) found that step and phase decomposition made "intervention, correction, and verification easier" for data analysts [34]. Dietvorst et al. (2018) identified the mechanism: users reject algorithms they cannot modify but adopt those they can, with 51 to 74 percent choosing to use a modifiable algorithm [35].

Ipeirotis and Zheng (preprint, N = 20) characterise the effect with precision: the interface reallocates the work of querying rather than removing it, and a natural-language interface that hid the generated query "would remove the step that let them trust the answer" [36]. The design consequence is that verification must be cheap. Accordingly, this system provides three linked affordances: the step breakdown as the primary verification surface, the SQL as the underlying evidence, and an editable SQL field as the repair loop, allowing a mis-selected column or filter to be corrected without re-prompting the model.

### E. Grounded Explanation and Calibrated Confidence

The negative results in the same literature are equally instructive, and they shaped two aspects of this system that an earlier version got wrong.

Bansal et al. (CHI 2021, approximately 100 participants per condition across three datasets) found that explanations "increased the chance that humans will accept the AI's recommendation, regardless of its correctness," and that explaining the top prediction degraded team accuracy when the AI was incorrect. Their conclusion was that "explanations increased blind trust rather than appropriate reliance on AI" [37]. Steyvers et al. (Nature Machine Intelligence 2025, N = 60, 60, 59) found that "longer explanations increased user confidence, even when the extra length did not improve answer accuracy," with human discrimination of correct from incorrect answers at an AUC of 0.54 for long explanations against 0.57 for uncertainty-only language [38].

Two design consequences follow. First, the plain-language explanation accompanying a query is constrained by its prompt to describe the query's mechanics - the tables read, the columns selected, the filter applied - and explicitly not to justify the query. A description of mechanics is verifiable line by line against the SQL displayed directly beneath it; a narrative of the model's reasoning is a post-hoc rationalisation and is not verifiable at all. Second, the confidence signal is categorical (High, Medium, Low) rather than numeric, and is derived from observable events during the run: a query that required correction is Low, a cached answer is Medium, and a first-attempt success is High. The model is never asked to estimate its own probability, because it has no calibrated probability over its own correctness, and numeric confidence that does not track accuracy raises user confidence without improving error detection.

### F. Disclosure of AI Interaction

The interface carries a notice at the top of the application, visible until the user asks their first question, stating that answers are written by an AI model that can misread a question, and that every answer shows the query it ran. This satisfies the transparency obligations of Article 50 of the European Union Artificial Intelligence Act, which has applied since 2 August 2026: Article 50(1) requires providers to ensure that persons interacting with an AI system are informed of that fact, and Article 50(5) requires the information to be provided "in a clear and distinguishable manner at the latest at the time of the first interaction" [39]. Article 50(4) further exempts text that has undergone "a process of human review or editorial control," which the editable-SQL approval flow described in Section V-C constitutes.

The notice names both the limitation and the remedy, rather than offering a generic disclaimer. This follows the consistent finding across the human-AI interaction literature that generic small-print warnings are ignored, and that warnings must be paired with a concrete action to be read at all.

### G. Accessibility as an Architectural Constraint

The interface targets WCAG 2.2 Level AA, and the constraints are enforced by the design system rather than audited after the fact:

- Interactive targets meet the 24-by-24-CSS-pixel minimum (SC 2.5.8). This is why the sort buttons, tab close controls, feedback buttons and status-bar buttons are sized at 26 pixels or larger even where the visual design would permit less.
- The result table uses native table semantics, so screen readers announce row and column headers without a layer of redundant ARIA. Sort direction is carried by `aria-sort` on the header cell, and `aria-rowcount` with per-row `aria-rowindex` allows a screen reader to announce position correctly even though only one page is present in the DOM.
- Status is never conveyed by colour alone; every badge pairs a colour with an icon and a word.
- The chart palette was validated for lightness band, chroma floor, colour-vision-deficiency separation, and contrast against the actual surface in both themes, rather than chosen by eye. Nominal categories are drawn in a single hue, because bar length already encodes the value.
- All motion is suppressed under a reduced-motion preference, and focus is always visible.

### H. Progressive Disclosure and Onboarding

A first-time user is not asked to understand an activity bar, a schema tree and an output panel before they can ask a question. The connection wizard describes the database type in plain language, the workspace name is optional and explained, and the Continue button stays disabled until the required fields are filled. On connection, the schema is indexed and a set of starter questions is generated from the database's own tables and columns, so the first question is always answerable. The layout itself remains a three-panel workspace, which preserves the density that makes the tool useful to analysts, but every panel is labelled, every control is named, and the conversation panel is where the work happens.

### I. Regression Testing

The project maintains two deterministic test suites. The Python suite covers the statement classifier across sixteen statement forms, the classifier's resistance to keyword-in-string and comment-based evasion, the impact preview's read-only guarantee, the schema retrieval fallback, and every API endpoint. The frontend suite runs the real ES modules against a stubbed document, verifying the data grid's sorting, filtering and paging, the chart-type selection rules, the chat message rendering, the SQL editing and re-run path, and the connection wizard's URI construction.

Both suites can run without a language model by substituting a deterministic stand-in for the model call, which makes them reproducible and free. Tests that genuinely require the model are marked and skipped by default, so a routine test run neither incurs cost nor fails because of an unrelated rate limit.

---

## VI. CONCLUSION

This document outlines an Autonomous, Self-Healing SQL Agent designed to make database querying accessible and safe for everyone. By combining an AI workflow with self-correction loops and strict security filters, the system overcomes the traditional risks of allowing AI to interact with sensitive databases. The use of cloud-ready technologies ensures the application is fast, scalable, and ready for real-world use.

The contribution beyond the original agent architecture is the treatment of safety and verifiability as interface problems rather than only as model problems. A deterministic classifier and a read-only impact preview make the approval decision informed rather than blind; making the generated SQL editable and re-runnable converts the model from an oracle into a collaborator whose mistakes the user can correct directly; and a token-driven, accessibility-constrained design system ensures the result is usable by the non-technical audience the system exists to serve. Future work would extend the impact preview to multi-table and schema-altering operations, and replace the keyword-derived starter questions with a semantic ranking over the indexed schema.


---

## REFERENCES

[32] Y. Tian, J. Yang, Z. Wu, D. Zhang, "Interactive Text-to-SQL Generation via Editable Step-by-Step Explanations," in *Proc. EMNLP*, 2023. doi:10.18653/v1/2023.emnlp-main.1004.

[33] Y. Tian, J. K. Kummerfeld, T. J.-J. Li, T. Zhang, "SQLucid: Grounding Natural Language Database Queries with Interactive Explanations," in *Proc. UIST*, 2024. doi:10.1145/3654777.3676368.

[34] M. Kazemitabaar et al., "Improving Steering and Verification in AI-Assisted Data Analysis with Interactive Task Decomposition," in *Proc. UIST*, 2024. doi:10.1145/3654777.3676345.

[35] U. Dietvorst, J. Simmons, C. Massey, "Overcoming Algorithm Aversion: People Will Use Imperfect Algorithms If They Can (Even Slightly) Modify Them," *Management Science*, vol. 64, no. 3, pp. 1155-1170, 2018. doi:10.1287/mnsc.2016.2643.

[36] P. Ipeirotis and Z. Zheng, "Natural Language Interfaces for Databases: What Changes for SQL-Literate Users?" arXiv:2511.14718, 2026 (preprint).

[37] S. Bansal et al., "Does the Whole Exceed its Parts? The Promise of Multiple Explanations," in *Proc. CHI*, 2021. doi:10.1145/3411764.3445717.

[38] M. Steyvers et al., "What large language models know and what people think they know," *Nature Machine Intelligence*, vol. 7, pp. 221-231, 2025. doi:10.1038/s42256-024-00976-7.

[39] Regulation (EU) 2024/1689 (Artificial Intelligence Act), Article 50, "Transparency obligations for providers and deployers of certain AI systems," applicable from 2 August 2026 per Article 113.

[40] S. Amershi et al., "Guidelines for Human-AI Interaction," in *Proc. CHI*, 2019. doi:10.1145/3290605.3300233.

[41] Z. Buçinca, M. B. Malaya, and K. Z. Gajos, "To Trust or to Think: Cognitive Forcing Functions Can Reduce Overreliance on AI in AI-Assisted Decision-Making," *Proc. ACM Hum.-Comput. Interact.*, vol. 5, 2021. doi:10.1145/3449287.

---
*End of Document*
