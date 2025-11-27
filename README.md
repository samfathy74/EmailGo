# EmailGo - Tactical Email Marketing System

EmailGo is a powerful, self-hosted email marketing and CRM solution designed with a tactical "Warzone" aesthetic. It allows you to manage contacts, create HTML email templates, run multi-server email campaigns, and track replies in real-time.

![EmailGo Dashboard](https://via.placeholder.com/800x400?text=EmailGo+Dashboard+Preview)

## 🚀 Features

### 🛡️ Core Operations
*   **Tactical Dashboard**: Real-time overview of active units (contacts), lifetime missions (campaigns), and success rates. Includes visual charts for sending trends and campaign status.
*   **Campaign Management**: Create, duplicate, and run multiple campaigns simultaneously. Supports both database-stored and file-based templates.
*   **Contact Management**: Organize contacts into groups, import from Excel/JSON, or add manually.
*   **Template System**: Built-in HTML editor for creating reusable email templates.

### 📡 Communications
*   **Multi-Server Support**: Configure multiple SMTP/IMAP servers. Rotate between them or assign specific servers for primary operations.
*   **Reply Tracking**: Connects to your email inbox via IMAP to fetch and display replies directly within the system.
*   **Follow-up System**: Reply to leads or resend campaigns directly from the "Replies" interface.

### 🌍 Localization & UI
*   **Bilingual Interface**: Full support for **English** and **Arabic** (RTL layout).
*   **Dark Mode**: Toggle between light and dark themes for optimal visibility in any environment.
*   **Responsive Design**: Fully functional on desktop, tablet, and mobile devices.

## 🛠️ Technology Stack
*   **Backend**: Python (Flask), SQLAlchemy, SQLite
*   **Frontend**: HTML5, Tailwind CSS (Local), JavaScript
*   **Libraries**: Chart.js (Visualizations), Marked.js (Markdown parsing), OpenPyXL (Excel import)

## 📦 Installation

1.  **Clone the repository**
    ```bash
    git clone https://github.com/yourusername/emailgo.git
    cd emailgo
    ```

2.  **Create a virtual environment**
    ```bash
    python -m venv venv
    # Windows
    venv\Scripts\activate
    # Linux/Mac
    source venv/bin/activate
    ```

3.  **Install dependencies**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Initialize the database**
    The application will automatically create the database (`instance/email_marketing.db`) on the first run.

5.  **Run the application**
    ```bash
    python app.py
    ```

6.  **Access the system**
    Open your browser and navigate to `http://127.0.0.1:5000`.
    *   **Default Login**: `admin` / `password`

## 📖 Usage Guide

### 1. Setup Servers
Go to **Settings** and add your SMTP/IMAP credentials (e.g., Gmail App Password). Set one server as "Primary" for sending.

### 2. Import Contacts
Navigate to **Contacts**, create a group (e.g., "Leads 2025"), and import your `.xlsx` or `.json` contact list.

### 3. Create a Template
Go to **Templates** and design your email. You can use standard HTML/CSS.

### 4. Launch a Campaign
Head to **Campaigns**, click "New Campaign", select your target group and template. Once created, click **Start** to begin the mission.

### 5. Monitor & Reply
Check the **Dashboard** for live progress. Go to **Replies** to fetch incoming responses and engage with your leads.

## 🔒 Security Note
*   This system is intended for **local use** or deployment on a **secure private network**.
*   Ensure `DEBUG` mode is disabled in `app.py` before deploying to a production environment.
*   Change the default admin password and `SECRET_KEY` immediately after installation.

## 📄 License
[MIT License](LICENSE)
