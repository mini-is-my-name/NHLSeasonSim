import requests
import json
from datetime import datetime
import pandas as pd
import numpy as np
import random
from tabulate import tabulate

# declare API URL as constant
API_URL = "https://api-web.nhle.com/v1/"
teams=['ANA','BOS','BUF','CAR','CBJ','CGY','CHI','COL','DAL','DET','EDM','FLA','LAK','MIN','MTL','NJD','NSH','NYI','NYR','OTT','PHI','PIT','SEA','SJS','STL','TBL','TOR','UTA','VAN','VGK','WPG','WSH']
today=datetime.today().strftime('%Y-%m-%d')

# define function to filter out games that are not happening today or in the future
def schedfilt(dict):
	filtgames={}
	for i in dict:
		if dict[i]['gameDate'] >= today:
			game_id=dict[i]['id']
			game_id=str(game_id)
			filtgames.update({game_id: dict[i]})
	return filtgames

# define function to pull a team's filtered season schedule
def schedpull(team):
	response = requests.get(API_URL + f"club-schedule-season/{team}/now")
	api_pull = response.json()
	api_pull=api_pull['games']
	games={}
	for i in api_pull:
		game_id=i['id']
		game_id=str(game_id)
		games.update({game_id: i})
	filtered=schedfilt(games)
	return filtered

#define function to add games from internal dict to external dict
def addgames(team,target):
	temp_dict=schedpull(team)
	for i in temp_dict:
		game_id=temp_dict[i]['id']
		game_id=str(game_id)
		target.update({game_id: temp_dict[i]})

# Call API for each team and add their remaining games to the gamedata dict
gamedata={}
for t in teams:
	print(f"Pulling {t}'s remaining games...")
	addgames(t,gamedata)

# temp func to open saved json file because doing the api call for every team takes a while
#def js_r(filename: str):
#    with open(filename) as f_in:
#        return json.load(f_in)
#gamedata=js_r('data.json')

#import elo data from google sheet
print("Importing Elo data...")
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow,Flow
from google.auth.transport.requests import Request
import os
import pickle

SCOPES=['https://www.googleapis.com/auth/spreadsheets']
SAMPLE_SPREADSHEET_ID='<spreadsheet_id>'
SAMPLE_RANGE_NAME='<data_range>'

def main():
    global values_input, service
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES) # here enter the name of your downloaded JSON file
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    service = build('sheets', 'v4', credentials=creds)

    # Call the Sheets API
    sheet = service.spreadsheets()
    result_input = sheet.values().get(spreadsheetId=SAMPLE_SPREADSHEET_ID,
                                range=SAMPLE_RANGE_NAME).execute()
    values_input = result_input.get('values', [])

    if not values_input and not values_expansion:
        print('No data found.')

main()

elo_df=pd.DataFrame(values_input[1:], columns=values_input[0])
#elo_df=pd.DataFrame()
#elo_df['Abbr.']=teams
#elo_df['Team']=['a','b','c','d','a','b','c','d','a','b','c','d','a','b','c','d','a','b','c','d','a','b','c','d','a','b','c','d','a','b','c','d']
#elo_df['Elo']=[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32]
#elo_df['Pts']=elo_df['Elo']*5
#elo_df['RW']=elo_df['Elo']*4
#elo_df['ROW']=elo_df['Elo']*3
#elo_df['W']=elo_df['Elo']*2

elo_df.set_index('Abbr.', drop=False, inplace=True)
elo_df[['Pts','RW','ROW','W']] = elo_df[['Pts','RW','ROW','W']].apply(pd.to_numeric)

#define function to get elos for each remaining game
def getelos(gdict):
    home=[]
    away=[]
    homeelo=[]
    awayelo=[]
    for i in gdict:
        ht=gdict[i]['homeTeam']['abbrev']
        at=gdict[i]['awayTeam']['abbrev']
        h_elo=elo_df.at[ht,'Elo']
        a_elo=elo_df.at[at,'Elo']
        h_elo=float(h_elo)
        a_elo=float(a_elo)
        home.append(ht)
        away.append(at)
        homeelo.append(h_elo)
        awayelo.append(a_elo)
    return home,away,homeelo,awayelo

hometeams,awayteams,h_elos,a_elos=getelos(gamedata)
game_df=pd.DataFrame()
game_df['Home']=hometeams
game_df['Away']=awayteams
game_df['Home_elo']=h_elos
game_df['Away_elo']=a_elos
game_df['elo_delta']=game_df['Away_elo']-game_df['Home_elo']
game_df['Home_exp_val']=(1/(1+10**(game_df['elo_delta']/400)))
game_df['Draw_odds']=0.21875*(2.71828**(-((game_df['elo_delta'])**2)/60000)) # 0.21875 is the % of games that went to OT over the 21/22, 22/23, & 23/24 seasons. 2.71828 is e. 60000 was chosen arbitrarily, but appears to give good distribution.
game_df['Home_odds']=game_df['Home_exp_val']-game_df['Draw_odds']/2

def seasonsim():
    ind_loc=0
    sim_df=elo_df.copy()
    end=len(game_df['Home'])
    end-=1

    while ind_loc <= end:
        rand=random.random()
        hodds=1-game_df.at[ind_loc,'Home_odds']
        if rand <= game_df.at[ind_loc,'Draw_odds']:
            rand=random.random()
            if rand <= game_df.at[ind_loc,'Home_exp_val']:
                sim_df.at[game_df.at[ind_loc,'Home'],'Pts']+=2
                sim_df.at[game_df.at[ind_loc,'Home'],'ROW']+=1
                sim_df.at[game_df.at[ind_loc,'Home'],'W']+=1
                sim_df.at[game_df.at[ind_loc,'Away'],'Pts']+=1
            else:
                sim_df.at[game_df.at[ind_loc,'Away'],'Pts']+=2
                sim_df.at[game_df.at[ind_loc,'Away'],'ROW']+=1
                sim_df.at[game_df.at[ind_loc,'Away'],'W']+=1
                sim_df.at[game_df.at[ind_loc,'Home'],'Pts']+=1
        elif rand >= hodds:
            sim_df.at[game_df.at[ind_loc,'Home'],'Pts']+=2
            sim_df.at[game_df.at[ind_loc,'Home'],'ROW']+=1
            sim_df.at[game_df.at[ind_loc,'Home'],'W']+=1
            sim_df.at[game_df.at[ind_loc,'Home'],'RW']+=1
        else:
            sim_df.at[game_df.at[ind_loc,'Away'],'Pts']+=2
            sim_df.at[game_df.at[ind_loc,'Away'],'ROW']+=1
            sim_df.at[game_df.at[ind_loc,'Away'],'W']+=1
            sim_df.at[game_df.at[ind_loc,'Away'],'RW']+=1
        ind_loc+=1
    return sim_df

metro=['CAR','CBJ','NJD','NYI','NYR','PHI','PIT','WSH']
atlantic=['BOS','BUF','DET','FLA','MTL','OTT','TBL','TOR']
pacific=['ANA','CGY','EDM','LAK','SEA','SJS','VAN','VGK']
central=['CHI','COL','DAL','MIN','NSH','STL','UTA','WPG']
divisions=[atlantic,metro,pacific,central]
div_str=['atlantic','metro','pacific','central']
ploff_odds=pd.DataFrame()
ploff_odds['Team']=teams
ploff_odds[['Div1','Div2','Div3','WC1','WC2']]=0
ploff_odds.set_index('Team', inplace=True)

rounds=['Round 2','Conf. Final','Cup Final','Win Cup']
for i in rounds:
	ploff_odds[i]=0

#Define function to find the divisional playoff teams
def finddivteams(division):
	rows=[]
	for team in division:
		indicies=np.where(szn_sim == team)
		rows.append(int(indicies[0][0]))
	n=0
	ploff_teams=[]
	ploff_team_inds=[]
	while n < 3:
		team_add_ind=min(rows)
		rows.remove(team_add_ind)
		ploff_team_inds.append(team_add_ind)
		ploff_teams.append(szn_sim.iloc[team_add_ind,0])
		n+=1
	return ploff_teams, rows, ploff_team_inds

#Define function that finds wildcard teams
def findploffteams():
	east=[]
	west=[]
	conferences=[east,west]
	confs_str=['east','west']
	count=0
	ploff_div_wc_teams={}
	for div,div_name in zip(divisions,div_str):
		div_teams,rem_div_teams,div_team_inds=finddivteams(div)
		ploff_div_wc_teams.update({div_name:div_team_inds})
		for i,j in zip(div_teams,ploff_odds):
			ploff_odds.loc[i,j]+=1
		if count < 2:
			east.extend(rem_div_teams)
		else:
			west.extend(rem_div_teams)
		count+=1

	for conf,conf_key in zip(conferences,confs_str):
		wc_teams=[]
		wc_inds=[]
		count=0
		while count < 2:
			wc_add_ind=min(conf)
			conf.remove(wc_add_ind)
			wc_inds.append(wc_add_ind)
			wc_teams.append(szn_sim.iloc[wc_add_ind,0])
			count+=1
			titles=['WC1','WC2']
		ploff_div_wc_teams.update({conf_key:wc_inds})
		for i,j in zip(wc_teams,titles):
			ploff_odds.loc[i,j]+=1
	return ploff_div_wc_teams

#Define function that simulates each playoff round
def ploff_r_sim(team1,team2,fin_df_col):
	t1_temp=[]
	t2_temp=[]
	n_ser=0
	for i,j in zip(team1,team2):
		n_game=0
		t1w=0
		t2w=0
		gameresult=(1/(1+10**((float(elo_df.at[j,'Elo'])-float(elo_df.at[i,'Elo']))/400)))
		while n_game<7:
			rand=random.random()
			if gameresult>=rand:
				t1w+=1
			else:
				t2w+=1
			n_game+=1
		if n_ser % 2 == 0:
			if t1w>t2w:
				t1_temp.append(i)
			else:
				t1_temp.append(j)
		else:
			if t1w>t2w:
				t2_temp.append(i)
			else:
				t2_temp.append(j)
		n_ser+=1
	for t in t1_temp:
		ploff_odds.at[t,fin_df_col]+=1
	for t in t2_temp:
		ploff_odds.at[t,fin_df_col]+=1
	team1=t1_temp
	team2=t2_temp
	return(team1,team2)

#Define function to solve seeding and simulate playoffs
def cup_sim(ind_dict,df):
	t1=[]
	for div in div_str:
	    adds=ind_dict.get(div)
	    t1.extend(adds[0:2])

	t2=[]
	for div in div_str:
	    adds=ind_dict.get(div)
	    t2.append(adds[2])

	wc_e=ind_dict.get('east')
	wc_w=ind_dict.get('west')
	if ind_dict.get('atlantic')[0] > ind_dict.get('metro')[0]: #this is why prev. orders matter
	    t2.insert(0,wc_e[0])
	    wc_e.pop(0)
	else:
		t2.insert(0,wc_e[1])
		wc_e.pop(1)
	t2.insert(2,wc_e[0])
	if ind_dict.get('pacific')[0] > ind_dict.get('central')[0]: #this is why prev. orders matter
		t2.insert(4,wc_w[0])
		wc_w.pop(0)
	else:
		t2.insert(4,wc_w[1])
		wc_w.pop(1)
	t2.insert(6,wc_w[0])

	t1_abb=[] #this is prob redundant but too bad my fault for writing complementary code without the source
	t2_abb=[]
	for i in t1:
		t1_abb.append(df.iloc[i,0])
	for i in t2:
		t2_abb.append(df.iloc[i,0])
	t1_run=t1_abb
	t2_run=t2_abb
	logfile.write("These teams made playoffs:"+str(t1_run)+str(t2_run)+"\n") #could be fun to store this as a log file along with season standings
	for i in rounds:
		t1_run,t2_run=ploff_r_sim(t1_run,t2_run,i)
		logfile.write(f"These teams advanced to {i}:"+str(t1_run)+str(t2_run)+"\n") #could be fun to store this as a log file

logfile=open('simlog.txt', 'w')
logfile.write('')
logfile.close()
logfile=open('simlog.txt', 'a')

sim_no=0
number_of_sims=10000
while sim_no < number_of_sims:
	print("Simulating season #" + str(sim_no))
	logfile.write(f'\nSeason {sim_no}\n')
	szn_sim=seasonsim()
	#szn_sim=elo_df
	szn_sim.sort_values(by=['Pts','RW','ROW','W'], ascending=False, inplace=True)
	seeds_dict=findploffteams()
	cup_sim(seeds_dict,szn_sim)
	sim_no+=1

ploff_odds['Make Playoffs'] = ploff_odds.iloc[:,:5].sum(axis=1)
ploff_odds[['Div1','Div2','Div3','WC1','WC2','Round 2','Conf. Final','Cup Final','Win Cup','Make Playoffs']]=ploff_odds[['Div1','Div2','Div3','WC1','WC2','Round 2','Conf. Final','Cup Final','Win Cup','Make Playoffs']]*100/number_of_sims
ploff_odds.sort_values(by=['Win Cup', 'Make Playoffs'], ascending=False, inplace=True)
ploff_odds[['Div1','Div2','Div3','WC1','WC2','Round 2','Conf. Final','Cup Final','Win Cup','Make Playoffs']]=ploff_odds[['Div1','Div2','Div3','WC1','WC2','Round 2','Conf. Final','Cup Final','Win Cup','Make Playoffs']].astype(str)+'%'
ploff_odds=ploff_odds[['Div1','Div2','Div3','WC1','WC2','Make Playoffs','Round 2','Conf. Final','Cup Final','Win Cup']]

logfile.close()

outfile=open('simulationresults.txt', 'w')
outfile.write(tabulate(ploff_odds,headers='keys',tablefmt='psql'))
print("Done!")
outfile.close()

#dumps json as a file
#with open("data.json", "w") as f:
#	json.dump(gamedata, f, indent=4)

#https://www.reddit.com/r/hockey/comments/17skeu2/created_some_reference_documentation_for_the_new/?rdt=52711
