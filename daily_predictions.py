from features.predictions.predictions import live_data_predictions, join_current_market, join_current_squad
from features.predictions.preprocessing import preprocess_player_data, split_data
from features.predictions.modeling import train_model, evaluate_model
from kickbase_api.league import get_league_id
from kickbase_api.user import login
from features.notifier import send_mail
from features.predictions.data_handler import (
    create_player_data_table,
    check_if_data_reload_needed,
    save_player_data_to_db,
    load_player_data_from_db,
)
from features.budgets import calc_manager_budgets
from IPython.display import display
from dotenv import load_dotenv
import os, pandas as pd

# Load environment variables from .env file
load_dotenv() 

# ----------------- Notes & TODOs -----------------

# TODO Fix the UTC timezone problems in the github actions scheduling
# TODO Add prediction of 3, 7 days, to give more context
# TODO Based upon the overpay of the other users, calculate a max price to pay for a player
# TODO Add features like starting 11 probability, injuries, ...
# TODO Improve budget calculation, weird bug that for me the budgets is 513929 off, idk why, checked everything

# ----------------- SYSTEM PARAMETERS -----------------
# Should be left unchanged unless you know what you're doing

last_mv_values = 365    # in days, max 365
last_pfm_values = 50    # in matchdays, max idk

# which features to use for training and prediction
features = [
    "p", "mv", "days_to_next", 
    "mv_change_1d", "mv_trend_1d", 
    "mv_change_3d", "mv_vol_3d",
    "mv_trend_7d", "market_divergence"
]

# what column to learn and predict on
target = "mv_target_clipped"

# Set dot as thousands separator for better readability
pd.options.display.float_format = lambda x: '{:,.0f}'.format(x).replace(',', '.')

# Show all columns when displaying dataframes
pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", None)
pd.set_option("display.width", 1000)

# ----------------- USER SETTINGS -----------------
# Adjust these settings to your preferences

competition_ids = [1]                   # 1 = Bundesliga, 2 = 2. Bundesliga, 3 = La Liga
league_name = "SGE4EVER 25/26"          # Name of your league, must be exact match, can be done via env or hardcoded
start_budget = 50_000_000               # Starting budget of your league, used to calculate current budgets of other managers
league_start_date = "2025-08-01"        # Start date of your league, used to filter activities, format: YYYY-MM-DD
email = os.getenv("EMAIL_USER")         # Email to send recommendations to, can be the same as EMAIL_USER or different

# ---------------------------------------------------

# Load environment variables and login to kickbase
USERNAME = os.getenv("KICK_USER") # DO NOT CHANGE THIS, YOU MUST SET THOSE IN GITHUB SECRETS OR A .env FILE
PASSWORD = os.getenv("KICK_PASS") # DO NOT CHANGE THIS, YOU MUST SET THOSE IN GITHUB SECRETS OR A .env FILE
token = login(USERNAME, PASSWORD)
print("\nLogged in to Kickbase.")

# Get league ID
league_id = get_league_id(token, league_name)

# Calculate (estimated) budgets of all managers in the league
manager_budgets_df = calc_manager_budgets(token, league_id, league_start_date, start_budget)
print("\n=== Manager Budgets ===")
display(manager_budgets_df)

# Data handling
create_player_data_table()
reload_data = check_if_data_reload_needed()
save_player_data_to_db(token, competition_ids, last_mv_values, last_pfm_values, reload_data)
player_df = load_player_data_from_db()
print("\nData loaded from database.")

# Preprocess the data and spit the data
proc_player_df, today_df = preprocess_player_data(player_df)
X_train, X_test, y_train, y_test = split_data(proc_player_df, features, target)
print("\nData preprocessed.")

# Train and evaluate the model
model = train_model(X_train, y_train)
signs_percent, rmse, mae, r2 = evaluate_model(model, X_test, y_test)
print(f"\nModel evaluation:\nSigns correct: {signs_percent:.2f}%\nRMSE: {rmse:.2f}\nMAE: {mae:.2f}\nR2: {r2:.2f}")

# Make live data predictions
live_predictions_df = live_data_predictions(today_df, model, features)

# Join with current available players on the market
market_recommendations_df = join_current_market(token, league_id, live_predictions_df)
print("\n=== Market Recommendations ===")
display(market_recommendations_df)

# Join with current players on the team
squad_recommendations_df = join_current_squad(token, league_id, live_predictions_df)
print("\n=== Squad Recommendations ===")
display(squad_recommendations_df)

# Send email with recommendations
send_mail(manager_budgets_df, market_recommendations_df, squad_recommendations_df, email)
