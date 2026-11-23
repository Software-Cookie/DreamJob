"""Skill and job-title vocabularies used by the matcher.

Format of SKILLS_RAW: one skill per line -> "Canonical | alias | alias ...".
An alias that starts with "=" is matched case-sensitively (for words that are
also normal English, e.g. "Go", "Swift", "Excel", "R").
"""

SKILLS_RAW = """
Python | python3
Java | =Java | J2EE | Java EE
JavaScript | JS | ES6 | ECMAScript | Vanilla JS
TypeScript | TS
Go | Golang | =Go
Rust | =Rust
C++ | cpp | C/C++
C# | csharp | C Sharp
.NET | dotnet | .NET Core | ASP.NET | ASP.NET Core
Ruby | =Ruby
Ruby on Rails | Rails | RoR
PHP
Laravel
Symfony
Kotlin
Swift | =Swift | SwiftUI
Objective-C | ObjC
Scala
Elixir
Erlang
Haskell
Clojure
Perl
Dart
Lua
R | =R | RStudio
MATLAB
Julia | =Julia
Bash | Shell Scripting | Zsh
PowerShell
SQL | T-SQL | PL/SQL
NoSQL
GraphQL
REST APIs | REST | RESTful | REST API | RESTful APIs
gRPC
WebSockets | WebSocket
HTML | HTML5
CSS | CSS3
Sass | SCSS
Tailwind CSS | Tailwind | TailwindCSS
Bootstrap | =Bootstrap
React | React.js | ReactJS
Next.js | NextJS
Redux
Vue.js | Vue | VueJS | Nuxt | Nuxt.js
Angular | AngularJS
Svelte | SvelteKit
jQuery
Node.js | NodeJS | =Node
Express.js | ExpressJS
NestJS | Nest.js
Deno
Django | Django REST Framework | DRF
Flask
FastAPI
Spring Boot | Spring Framework | Spring MVC
Hibernate
Microservices | Microservice
Serverless
React Native
Flutter
Android | Android SDK
iOS | iOS Development
Xamarin
Ionic
Electron
Unity | =Unity | Unity3D
Unreal Engine | Unreal
WordPress
Shopify
Webflow
Magento
Salesforce | SFDC | Salesforce CRM
SAP
Oracle | Oracle DB
PostgreSQL | Postgres
MySQL
MariaDB
SQLite
Microsoft SQL Server | MSSQL | SQL Server
MongoDB | Mongo
Redis
Cassandra
DynamoDB
Elasticsearch | Elastic Search | OpenSearch | ELK
Firebase
Supabase
Snowflake
BigQuery
Redshift
Databricks
Apache Spark | Spark | PySpark
Hadoop
Kafka | Apache Kafka
RabbitMQ
Airflow | Apache Airflow
dbt
ETL | ELT
Data Warehousing | Data Warehouse
Data Modeling | Data Modelling
Data Pipelines | Data Pipeline
Pandas
NumPy
SciPy
scikit-learn | sklearn | scikit learn
TensorFlow
PyTorch
Keras
Hugging Face | HuggingFace | Transformers
LangChain
LlamaIndex
OpenAI API | OpenAI | GPT
LLMs | LLM | Large Language Models | Generative AI | GenAI
RAG | Retrieval Augmented Generation
Prompt Engineering
Machine Learning | ML
Deep Learning
NLP | Natural Language Processing
Computer Vision | OpenCV
MLOps
Statistics | Statistical Analysis
A/B Testing | AB Testing | Experimentation
Data Analysis | Data Analytics
Data Visualization | Data Viz
Tableau
Power BI | PowerBI
Looker | Looker Studio
Microsoft Excel | MS Excel | =Excel | Advanced Excel
Google Sheets
VBA
Jupyter | Jupyter Notebook
AWS | Amazon Web Services | EC2 | S3 | Lambda | AWS Lambda
Azure | Microsoft Azure
GCP | Google Cloud | Google Cloud Platform
Docker | Containers
Kubernetes | K8s | EKS | GKE | AKS
Helm
Terraform
Ansible
Pulumi
CloudFormation
Jenkins
GitHub Actions
GitLab CI | GitLab
CircleCI
CI/CD | Continuous Integration | Continuous Delivery | Continuous Deployment
DevOps
SRE | Site Reliability Engineering
Linux | Unix | Ubuntu
Nginx
Apache HTTP Server | Apache HTTP
Prometheus
Grafana
Datadog
Splunk
New Relic
Observability
Git | GitHub | Bitbucket
Jira
Confluence
Agile | Agile Methodology
Scrum | Scrum Master
Kanban
Test Automation | Automation Testing | Automated Testing
Selenium
Cypress
Playwright
Jest
Pytest
JUnit
Unit Testing | Unit Tests | TDD | Test Driven Development
QA | Quality Assurance | Manual Testing
Postman
API Testing
Performance Testing | Load Testing | JMeter
Cybersecurity | Information Security | InfoSec | Cyber Security
Penetration Testing | Pentesting | Ethical Hacking
SIEM
IAM | Identity and Access Management
OAuth | OAuth2 | OpenID Connect | SSO
Networking | TCP/IP | DNS
Blockchain | Web3
Solidity
Ethereum
Embedded Systems | Embedded | Firmware
IoT | Internet of Things
FPGA | VHDL | Verilog
PLC
AutoCAD
SolidWorks
CAD
Revit
GIS | ArcGIS | QGIS
System Design | Distributed Systems
Data Structures | Algorithms | DSA
Object-Oriented Programming | OOP | OOPS
Design Patterns
Figma
Sketch | =Sketch
Adobe XD
Adobe Photoshop | Photoshop
Adobe Illustrator | Illustrator
Adobe InDesign | InDesign
Adobe After Effects | After Effects
Adobe Premiere Pro | Premiere Pro | Premiere
Canva
UI Design | User Interface Design | UI
UX Design | User Experience | UX | UX Research | User Research
Wireframing | Wireframes
Prototyping
=Design Systems | =Design System
Interaction Design
Usability Testing
Accessibility | WCAG | a11y
Graphic Design
Motion Design | Motion Graphics | Animation
Video Editing
3D Modeling | Blender | Maya
Product Management | Product Strategy
Product Roadmap | Roadmapping
Product Discovery
User Stories
Stakeholder Management
Project Management | PMP | PRINCE2
Program Management
Risk Management
Change Management
Business Analysis | Business Analyst | Requirements Gathering
Process Improvement | Six Sigma | Lean Six Sigma
Operations Management
Supply Chain | Supply Chain Management | Logistics
Procurement | Purchasing
Inventory Management
Vendor Management
SEO | Search Engine Optimization
SEM | Search Engine Marketing | PPC | Google Ads | Paid Search
Content Marketing | Content Strategy
Social Media Marketing | Social Media | SMM
Email Marketing | Mailchimp | Klaviyo
Marketing Automation | Marketo | Pardot
Performance Marketing | Paid Media | Paid Social | Meta Ads | Facebook Ads
Growth Marketing | Growth Hacking
Brand Strategy | Branding | Brand Management
Digital Marketing
Product Marketing | Go-to-Market | GTM
Google Analytics | GA4
Copywriting | Copy Writing
Content Writing | Blogging
Technical Writing
Editing | Proofreading
Public Relations | Corporate Communications
HubSpot
CRM | Customer Relationship Management
B2B Sales | B2B
B2C | Consumer Sales
SaaS | Software as a Service
Lead Generation | Prospecting | Cold Calling | Outbound
Account Management | Key Account Management
Business Development | BD
Negotiation
Customer Success
Customer Support | Customer Service | Technical Support | Help Desk
Zendesk
Intercom
Accounting | Bookkeeping
Financial Analysis | Financial Modeling | Financial Modelling
FP&A | Financial Planning
Budgeting | Forecasting
Auditing | Audit
Taxation | Tax Accounting | Tax Compliance | GST | Income Tax
QuickBooks
Xero
Tally | Tally ERP
IFRS | GAAP | US GAAP
Accounts Payable
Accounts Receivable
Payroll
Investment Banking
Valuation
Risk Analysis | Credit Risk
Compliance | Regulatory Compliance | KYC | AML
=Recruiting | Recruitment | Talent Acquisition | Full Cycle Recruiting | Technical Recruiting | Sourcing Candidates
HR | Human Resources | HRBP | HR Generalist
Employee Onboarding
Employee Relations
Compensation and Benefits | Total Rewards
Workday
Training and Development | L&D | Learning and Development
Teaching | Tutoring | Curriculum Development | Lesson Planning
Nursing | Registered Nurse | RN
Patient Care
Clinical Research | Clinical Trials
Healthcare Systems | EHR | EMR | HIPAA
Pharmacy | Pharmaceutical
Medical Coding | ICD-10
Legal Research | Contract Drafting | Litigation
Translation | Localization
Data Entry
Virtual Assistant | Administrative Support | Office Administration
Event Management | Event Planning
Leadership | Team Leadership | People Management | Mentoring
Communication | Communication Skills | Verbal Communication | Written Communication
Problem Solving | Critical Thinking
Presentation Skills | Public Speaking
Time Management
English | Fluent English
German | =German
French | =French
Spanish | =Spanish
"""

# Title phrases -> role family. Longer phrases are preferred when inferring a résumé's title.
TITLE_FAMILIES = {
    "software": [
        "software engineer", "software developer", "backend engineer", "backend developer",
        "back end developer", "frontend engineer", "frontend developer", "front end developer",
        "full stack developer", "full stack engineer", "fullstack developer", "fullstack engineer",
        "web developer", "mobile developer", "android developer", "ios developer",
        "application developer", "programmer", "java developer", "python developer",
        "react developer", "node developer", "net developer", "php developer", "ruby developer",
        "golang developer", "flutter developer", "game developer", "embedded engineer",
        "firmware engineer", "engineering manager", "tech lead", "technical lead",
        "solutions architect", "software architect", "member of technical staff", "sde",
        "salesforce developer", "wordpress developer", "blockchain developer",
    ],
    "devops": [
        "devops engineer", "site reliability engineer", "sre", "platform engineer",
        "cloud engineer", "infrastructure engineer", "systems administrator", "system administrator",
        "network engineer", "cloud architect", "release engineer", "build engineer",
    ],
    "security": [
        "security engineer", "security analyst", "cybersecurity analyst", "penetration tester",
        "soc analyst", "information security analyst", "application security engineer",
    ],
    "qa": [
        "qa engineer", "test engineer", "sdet", "quality assurance engineer", "qa analyst",
        "automation engineer", "software tester", "qa tester", "test automation engineer",
    ],
    "data": [
        "data scientist", "data analyst", "data engineer", "machine learning engineer",
        "ml engineer", "ai engineer", "business intelligence analyst", "bi analyst", "bi developer",
        "analytics engineer", "research scientist", "applied scientist", "statistician",
        "quantitative analyst", "data architect", "analytics manager", "deep learning engineer",
        "nlp engineer", "computer vision engineer", "mlops engineer", "database administrator",
    ],
    "design": [
        "product designer", "ux designer", "ui designer", "ui ux designer", "ux ui designer",
        "graphic designer", "visual designer", "interaction designer", "ux researcher",
        "web designer", "motion designer", "brand designer", "design lead", "creative director",
        "illustrator", "video editor", "3d artist", "art director",
    ],
    "product": [
        "product manager", "product owner", "technical product manager", "group product manager",
        "product lead", "head of product", "associate product manager",
    ],
    "project": [
        "project manager", "program manager", "scrum master", "delivery manager",
        "project coordinator", "technical program manager", "agile coach", "pmo",
    ],
    "business": [
        "business analyst", "operations analyst", "operations manager", "strategy analyst",
        "management consultant", "consultant", "business operations", "chief of staff",
        "supply chain analyst", "supply chain manager", "logistics coordinator", "procurement specialist",
        "buyer", "operations coordinator", "process analyst",
    ],
    "marketing": [
        "marketing manager", "digital marketing manager", "digital marketing specialist",
        "marketing specialist", "seo specialist", "seo manager", "content marketer",
        "content marketing manager", "growth marketer", "growth manager", "social media manager",
        "performance marketing manager", "product marketing manager", "brand manager",
        "marketing coordinator", "email marketing specialist", "community manager",
        "marketing analyst", "head of marketing", "demand generation manager",
    ],
    "content": [
        "content writer", "copywriter", "technical writer", "editor", "content strategist",
        "journalist", "content creator", "communications manager", "pr manager", "translator",
    ],
    "sales": [
        "sales representative", "account executive", "sales manager", "business development manager",
        "business development representative", "sales development representative", "bdr", "sdr",
        "account manager", "key account manager", "sales executive", "inside sales",
        "sales engineer", "solutions engineer", "partnerships manager", "head of sales",
    ],
    "support": [
        "customer success manager", "customer support specialist", "customer service representative",
        "support engineer", "technical support engineer", "customer support representative",
        "support specialist", "help desk technician", "customer experience specialist",
        "implementation specialist", "onboarding specialist",
    ],
    "finance": [
        "accountant", "financial analyst", "finance manager", "controller", "auditor",
        "bookkeeper", "tax consultant", "fp&a analyst", "investment analyst", "credit analyst",
        "chartered accountant", "accounts payable specialist", "payroll specialist", "cfo",
        "risk analyst", "compliance analyst", "compliance officer",
    ],
    "hr": [
        "recruiter", "technical recruiter", "talent acquisition specialist", "hr manager",
        "hr generalist", "hr business partner", "people operations", "hr coordinator",
        "talent acquisition manager", "sourcer", "people partner",
    ],
    "admin": [
        "executive assistant", "administrative assistant", "office manager", "virtual assistant",
        "data entry operator", "receptionist", "personal assistant",
    ],
    "healthcare": [
        "registered nurse", "nurse", "physician", "medical assistant", "pharmacist",
        "clinical research associate", "medical coder", "physical therapist", "therapist",
        "dentist", "healthcare administrator", "caregiver",
    ],
    "education": [
        "teacher", "tutor", "instructor", "lecturer", "professor", "curriculum developer",
        "instructional designer", "teaching assistant", "trainer",
    ],
    "legal": ["lawyer", "attorney", "paralegal", "legal counsel", "legal assistant", "advocate"],
    "engineering": [
        "mechanical engineer", "electrical engineer", "civil engineer", "chemical engineer",
        "manufacturing engineer", "hardware engineer", "electronics engineer", "process engineer",
        "industrial engineer", "structural engineer", "architect", "quality engineer",
    ],
}

# Skills that say little on their own; weighted lower in scoring.
SOFT_SKILLS = {
    "Leadership", "Communication", "Problem Solving", "Presentation Skills", "Time Management",
    "English", "Agile", "Git", "Jira", "Confluence", "Microsoft Excel", "Google Sheets",
    "Networking", "Compliance", "SaaS", "B2B Sales", "Statistics", "Data Analysis",
}
