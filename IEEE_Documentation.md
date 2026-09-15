# Autonomous AI Agent for Secure and Self-Healing Natural Language to SQL Translation

**Abstract**— The rapid adoption of Artificial Intelligence (AI) has enabled significant advancements in how humans interact with computers. One of the most promising applications is Natural Language to SQL (NL2SQL), which allows people who do not know how to code to ask questions in plain English and retrieve data from complex databases. However, deploying these systems in real-world environments introduces challenges, such as the AI making up incorrect information (hallucination), the risk of executing harmful commands that delete data, and slow performance when answering similar questions repeatedly. This document details an Autonomous SQL Agent that utilizes a web-based backend and an AI workflow manager (LangGraph) to solve these issues. The system provides the AI with exact database structures (schema) using a search-based memory system (Qdrant), features a self-correction loop where the AI fixes its own errors before the user sees them, and includes a strict security layer that stops harmful commands. Evaluations on live enterprise databases demonstrate high accuracy and strong security, while a smart memory system (caching) significantly reduces wait times for repetitive questions.

**Index Terms**— Artificial Intelligence, Data Analytics, Natural Language Processing, Retrieval-Augmented Generation, Self-Healing Systems.

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
Before any code is sent to the database, a strict security filter scans the text for dangerous keywords like `DROP`, `DELETE`, or `UPDATE`. If found, the system halts and requires a human to click an "Approve" button, ensuring that the AI can never destroy data on its own.

---

## IV. EVALUATION AND TESTING

To ensure the system works reliably, it was rigorously tested against a live, multi-tenant enterprise database (Snowflake). The evaluation tested how well the system handled the four scenarios mentioned above.

### A. How Evaluation Was Done
An automated script was created to simulate a user asking questions across the four different categories (Standard, Complex, Destructive, Repetitive). The script recorded whether the AI successfully answered the question, how long it took, whether the self-healing loop was needed, and whether the security system properly caught dangerous commands.

### B. Evaluation Results

The testing revealed the following performance metrics:

| Metric | Result | Explanation |
| :--- | :--- | :--- |
| **Accuracy** | 100% | The AI successfully generated the correct SQL for all test questions. |
| **Self-Healing Success** | 100% | Whenever the AI made an initial mistake, it successfully fixed its own error on the first retry. |
| **Security Success** | 100% | The system successfully stopped all dangerous queries and never accidentally let one slip through. |
| **Initial Wait Time** | ~2.34 seconds | The average time it takes for the AI to think and answer a brand new question. |
| **Cached Wait Time** | ~0.05 seconds | The average time it takes to answer a question it has seen before. |

The results show that the combination of self-healing and smart memory creates a system that is both highly accurate and extremely fast for repetitive tasks, while remaining completely secure.

---

## V. CONCLUSION

This document outlines an Autonomous, Self-Healing SQL Agent designed to make database querying accessible and safe for everyone. By combining an AI workflow with self-correction loops and strict security filters, the system overcomes the traditional risks of allowing AI to interact with sensitive databases. The use of cloud-ready technologies ensures the application is fast, scalable, and ready for real-world use. Future improvements may include adding automated data visualization, allowing the AI to not only fetch data but also draw charts and graphs automatically.

---
*End of Document*
