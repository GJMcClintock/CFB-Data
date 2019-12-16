import pandas as pd
import requests
import json
from tqdm import tqdm as tqdm
from scipy.stats import norm
import itertools
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# %% Get Games

years = [2019]
game_req = []
games = pd.DataFrame()
for year in tqdm(years, desc = 'fetch bowl games to get teams'):
    parameters = {"year":year, "seasonType":"postseason"}
    game_req = requests.get("https://api.collegefootballdata.com/games", params = parameters, verify=False)
    try:
        games = games.append(json.loads(game_req.text))
    except IndexError:
        pass
    continue

cur_games = pd.DataFrame()
for year in tqdm(years, desc = 'fetch current season games'):
    parameters = {"year":year, "seasonType":"regular"}
    game_req = requests.get("https://api.collegefootballdata.com/games", params = parameters, verify=False)
    try:
        cur_games = cur_games.append(json.loads(game_req.text))
    except IndexError:
        pass
    continue

years = list(range(2015,2020))
reg_games = pd.DataFrame()
for year in tqdm(years, desc = 'fetch reg season for past years'):
    parameters = {"year":year, "seasonType":"regular"}
    game_req = requests.get("https://api.collegefootballdata.com/games", params = parameters, verify=False)
    try:
        reg_games = reg_games.append(json.loads(game_req.text))
    except IndexError:
        pass
    continue
for year in tqdm(years, desc = 'fetch past bowl games'):
    parameters = {"year":year, "seasonType":"postseason"}
    game_req = requests.get("https://api.collegefootballdata.com/games", params = parameters, verify=False)
    try:
        reg_games = reg_games.append(json.loads(game_req.text))
    except IndexError:
        pass
    continue

#%% Get SP+
years = [2019]
sp_req = []
sp_ratings = pd.DataFrame()
for year in tqdm(years):
    parameters = {"year": year}
    sp_req = requests.get("https://api.collegefootballdata.com/ratings/sp", params=parameters, verify=False)
    sp_ratings = sp_ratings.append(json.loads(sp_req.text))
    
# clean up columns and remove the "National Averages"

sp_ratings = sp_ratings[['year','team','conference','rating','secondOrderWins','sos']]

sp_ratings = sp_ratings[sp_ratings['team'] != 'nationalAverages']

# clean up sp for joins
sp = sp_ratings[['team','rating']].copy()

sp_home = sp.rename(columns={'team':'home_team','rating':'home_rating'}).copy()
sp_away = sp.rename(columns={'team':'away_team','rating':'away_rating'}).copy()

#%% Get Conferences

cur_games = cur_games[cur_games['home_conference'].notnull()].copy()
home_conf = cur_games[['home_team','home_conference']].copy().drop_duplicates()
away_conf = cur_games[['home_team','home_conference']].copy().drop_duplicates()
away_conf.columns = ['away_team','away_conference']
#%% Generate Combos
    
team_list = games.home_team.tolist() + games.away_team.tolist()

team_list = pd.DataFrame(itertools.combinations(team_list, 2))

team_list.columns = ['home_team','away_team']

team_list = pd.merge(team_list, home_conf, on='home_team', how='left')
team_list = pd.merge(team_list, away_conf, on='away_team', how='left')

#%%
# Remove Previously Played Matchups
homekey = list(reg_games['home_team'] + reg_games['away_team'])
awaykey = list(reg_games['away_team'] + reg_games['home_team'])

team_list['homekey'] = team_list['home_team'] + team_list['away_team']
team_list = team_list[~team_list['homekey'].isin(homekey)].copy()

team_list['awaykey'] = team_list['away_team'] + team_list['home_team']
team_list = team_list[~team_list['awaykey'].isin(homekey)].copy()

playoff = ['LSU','Ohio State','Clemson', 'Oklahoma']
team_list = team_list[~team_list['home_team'].isin(playoff)].copy()
team_list = team_list[~team_list['away_team'].isin(playoff)].copy()

team_list = team_list[['home_team','home_conference','away_team','away_conference']]

team_list = team_list[~(team_list['home_conference']==team_list['away_conference'])].copy()



# %% add sp ratings to game list
bowls = pd.merge(team_list, sp_home, on=['home_team'], how='left')
bowls = pd.merge(bowls, sp_away, on=['away_team'], how='left')


# estimate spread and win probability

bowls['est_home_spread'] = bowls['home_rating'] - bowls['away_rating']

bowls['home_win_prob'] = norm.cdf(bowls['est_home_spread'] / 17)

bowls['abs'] = abs(bowls['est_home_spread'])

#%% Grab Top Bama Matchups and Check Threshold To See if All Teams are Covered
bowls = bowls.sort_values(by='abs').copy()
bama = bowls[(bowls['home_team'] == 'Alabama') | (bowls['away_team'] == 'Alabama')].head(5).copy()

df = bowls[bowls['abs'] < 3].copy()
team_check = list(set((list(df['home_team'])+ list(df['away_team']))))

        
#%% Loop Through Simulation

# Set number of simulations
sims = 1000

# Create large initial dummy spread to check against
mean_spread = 1000000


# Create list of past means
previous_means = []
for i in tqdm(range(0,sims)):
   
    # Randomize List and Set Threshold of Spread To Improve Speeed/Results
    df = bowls.sample(frac=1).reset_index(drop=True)
    df = df[df['abs'] < 3].copy().reset_index(drop=True)
    
    # Create scratch DF and add Bama game.
    scratch_df = pd.DataFrame().reindex_like(df).iloc[0:0]
    bama = bama.sample(frac=1).reset_index(drop=True)
    bama_game = pd.DataFrame(bama.iloc[0]).transpose()
    df = df.append(bama)
    
    # Check teams in Scratch DF and remove them from pool of available teams
    s = list(scratch_df['home_team']) + list(scratch_df['away_team'])
    df = df[~df['home_team'].isin(s)]
    df = df[~df['away_team'].isin(s)]
    # Grab Basket of Games For Remaining Teams
    j = len(df)
    while j > 0:
        fill = pd.DataFrame(df.iloc[0]).transpose()
        scratch_df = scratch_df.append(fill)
        s = list(scratch_df['home_team']) + list(scratch_df['away_team'])
        df = df[~df['home_team'].isin(s)]
        df = df[~df['away_team'].isin(s)]
        df = df.reset_index(drop=True)
        j = len(df)
    
    # Check Mean of Basket    
    scratch_mean = scratch_df['abs'].mean()
    sctrach_count = scratch_df['abs'].count()
    
    # Add to Output if Improvement
    if scratch_mean < mean_spread and sctrach_count == 37:
        scratch_df['variant'] = i
        output = pd.DataFrame().reindex_like(scratch_df).iloc[0:0]
        output = output.append(scratch_df)
        previous_means.append(mean_spread)
        mean_spread = scratch_mean
        i = i + 1
        scratch_df = pd.DataFrame().reindex_like(df).iloc[0:0]
    elif scratch_mean == mean_spread and sctrach_count == 37:
        scratch_df['variant'] = i
        output = output.append(scratch_df)
        i = i + 1
        scratch_df = pd.DataFrame().reindex_like(df).iloc[0:0]
    else:
        scratch_df = pd.DataFrame().reindex_like(df).iloc[0:0]
        i = i + 1
