import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
from datetime import datetime
import time

URLS_PARQUET = "urls.parquet"
parquet_file = "matches.parquet"

def get_page_content(url):
    """Récupère le contenu HTML d'une page"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        return None, str(e)

def parse_matches(html_content):
    """Parse le HTML pour extraire les informations des matchs"""
    soup = BeautifulSoup(html_content, 'html.parser')
    matches = []
    
    # Trouver tous les blocs de match avec header
    match_sections = soup.find_all('div', class_='tournament-category__match')
    
    for section in match_sections:
        match_info = {}
        
        # Extraire les infos du header (mat et horaire)
        header = section.find('div', class_='tournament-category__match-header')
        if header:
            # Mat et numéro de fight
            where_elem = header.find('div', class_='bracket-match-header__where')
            if where_elem:
                match_info['location'] = where_elem.get_text(strip=True)
            
            # Horaire
            when_elem = header.find('div', class_='bracket-match-header__when')
            if when_elem:
                match_info['time'] = when_elem.get_text(strip=True)
        
        # Extraire les compétiteurs
        match_card = section.find('div', class_='tournament-category__match-card')
        if match_card:
            competitors = match_card.find_all('div', class_='match-card__competitor')
            valid_competitors = []
            
            for competitor in competitors:
                # Vérifier si c'est un BYE
                bye_elem = competitor.find('div', class_='match-card__bye')
                if bye_elem:
                    continue
                
                # Vérifier si c'est un "Winner of Fight" (attente du gagnant)
                child_where_elem = competitor.find('div', class_='match-card__child-where')
                if child_where_elem and 'Winner of Fight' in child_where_elem.get_text():
                    competitor_info = {
                        'name': child_where_elem.get_text(strip=True),
                        'club': '',
                        'type': 'winner_waiting'
                    }
                    valid_competitors.append(competitor_info)
                    continue
                
                # Extraire le nom du compétiteur normal
                name_elem = competitor.find('div', class_='match-card__competitor-name')
                if name_elem and name_elem.get_text(strip=True):
                    competitor_info = {
                        'name': name_elem.get_text(strip=True),
                        'club': '',
                        'type': 'normal'
                    }
                    
                    # Extraire le club
                    club_elem = competitor.find('div', class_='match-card__club-name')
                    if club_elem:
                        competitor_info['club'] = club_elem.get_text(strip=True)
                    
                    # Extraire le numéro du compétiteur
                    number_elem = competitor.find('span', class_='match-card__competitor-n')
                    if number_elem:
                        competitor_info['number'] = number_elem.get_text(strip=True)
                    
                    valid_competitors.append(competitor_info)
            
            # Ne garder que les matchs avec au moins 1 compétiteur confirmé ou en attente (pas de BYE)
            if len(valid_competitors) >= 1:
                match_info['competitors'] = valid_competitors
                match_info['match_type'] = 'scheduled'
                matches.append(match_info)
    
    return matches

def display_matches(matches):
    """Affiche les matchs de manière claire"""
    if not matches:
        st.warning("Aucun match trouvé")
        return
    
    st.success(f"🥋 {len(matches)} match(s) trouvé(s)")
    df = pd.DataFrame(columns=["Nom", "Club", "Numero", "Mat", "Heure"])
    for i, match in enumerate(matches, 1):
        with st.container():
            
            # Compétiteurs
            competitors = match['competitors']
            
            if len(competitors) == 2:
                # Match avec 2 compétiteurs
                if competitors[0]['type'] == 'winner_waiting' and competitors[1]['type'] == 'winner_waiting':
                    continue
                else:
                    # Header avec mat et horaire
                    st.markdown("---")
                    col1, col2 = st.columns(2)
                    with col1:
                        if 'location' in match:
                            st.write(f"📍 **{match['location']}**")
                    with col2:
                        if 'time' in match:
                            st.write(f"🕐 **{match['time']}**")
                    
                    
                    st.write("**Combattants:**")
                    col1, col2, col3 = st.columns([5, 1, 5])

                    with col1:
                        comp1 = competitors[0]
                        if comp1['type'] == 'winner_waiting':
                            st.write(f"🟠 **{comp1['name']}**")
                        else:
                            st.write(f"🔴 **{comp1['name']}**")
                            if comp1['club']:
                                st.write(f"   _{comp1['club']}_")
                            if 'number' in comp1:
                                st.write(f"   Numéro: {comp1['number']}")
                                df.loc[len(df)] = [comp1['name'], comp1.get('club', ''), comp1.get('number', ''),
                                    match.get('location', ''), match.get('time', '')]
                            
                    
                    with col2:
                        st.write("**VS**")
                    
                    with col3:
                        comp2 = competitors[1]
                        if comp2['type'] == 'winner_waiting':
                            st.write(f"🟠 **{comp2['name']}**")
                        else:
                            st.write(f"🔵 **{comp2['name']}**")
                            if comp2['club']:
                                st.write(f"   _{comp2['club']}_")
                            if 'number' in comp2:
                                st.write(f"   Numéro: {comp2['number']}")
                                df.loc[len(df)] = [comp2['name'], comp2.get('club', ''), comp2.get('number', ''),
                                    match.get('location', ''), match.get('time', '')]
    df['Numero'] = pd.to_numeric(df['Numero'], errors='coerce')
    df = df[['Numero', 'Nom', 'Club', 'Mat', 'Heure']]
    df = df.sort_values(by='Numero', ascending=True)
    return df

def update_from_all_urls():
    if 'urls_df' not in st.session_state or st.session_state['urls_df'].empty:
        return
    updated_df = pd.DataFrame(columns=["Numero", "Nom", "Club", "Mat", "Heure"])

    for url in st.session_state['urls_df']['url'].unique():
        html = get_page_content(url)
        if html:
            matches = parse_matches(html)
            df = display_matches(matches)
            if df is not None and not df.empty:
                updated_df = pd.concat([updated_df, df], ignore_index=True)

    updated_df.drop_duplicates(inplace=True)
    updated_df = updated_df.sort_values(by='Heure', ascending=False)
    updated_df = updated_df.drop_duplicates(subset='Nom', keep='first')
    updated_df['Numero'] = pd.to_numeric(updated_df['Numero'], errors='coerce')
    updated_df = updated_df.sort_values(by='Numero')

    now = datetime.now().strftime('%H:%M')
    updated_df = updated_df[updated_df['Heure'] >= now]

    st.session_state['global_df'] = updated_df
    updated_df.to_parquet(parquet_file, index=False)



def main():
    st.title("🥋 BJJ Match Parser")
    
    if 'global_df' not in st.session_state:
        if os.path.exists(parquet_file):
            st.session_state['global_df'] = pd.read_parquet(parquet_file)
        else:
            st.session_state['global_df'] = pd.DataFrame(columns=["Numero", "Nom", "Club", "Mat", "Heure"])
            

    # Charger ou initialiser le fichier des URLs
    if 'urls_df' not in st.session_state:
        if os.path.exists(URLS_PARQUET):
            st.session_state['urls_df'] = pd.read_parquet(URLS_PARQUET)
        else:
            st.session_state['urls_df'] = pd.DataFrame(columns=["url"])
    

    default_url = "https://www.bjjcompsystem.com/tournaments/2816/categories/2660052"
    url = st.text_input("URL de la compétition:", value=default_url)
    
    if st.button("Analyser les matchs"):
        if url:
            with st.spinner("Récupération et analyse..."):
                html_content = get_page_content(url)
                
                if html_content:
                    matches = parse_matches(html_content)
                    all_data_df = display_matches(matches)
                    if 'global_df' not in st.session_state:
                        st.session_state['global_df'] = pd.DataFrame(columns=all_data_df.columns)
                    st.session_state['global_df'] = pd.concat([st.session_state['global_df'], all_data_df], ignore_index=True).drop_duplicates()
                    # Filtrage pour ne garder que les matchs les plus récents par numéro
                    st.session_state['global_df'] = st.session_state['global_df'].sort_values(by='Heure', ascending=False)
                    st.session_state['global_df'] = st.session_state['global_df'].drop_duplicates(subset='Nom', keep='first')
                    st.session_state['global_df'] = st.session_state['global_df'].sort_values(by='Numero')
                    st.session_state['global_df'].to_parquet(parquet_file, index=False)

                    # Ajouter l'URL à la session et sauvegarder si nouvelle
                    if url not in st.session_state['urls_df']['url'].values:
                        st.session_state['urls_df'] = pd.concat([
                            st.session_state['urls_df'],
                            pd.DataFrame([{"url": url}])
                        ], ignore_index=True).drop_duplicates()
                        st.session_state['urls_df'].to_parquet(URLS_PARQUET, index=False)

                else:
                    st.error("Impossible de récupérer le contenu de la page")
        else:
            st.error("Veuillez entrer une URL")
    
    # Afficher des instructions
    with st.expander("ℹ️ Comment ça marche"):
        st.markdown("""
        Cet outil analyse les pages de BJJ Comp System et extrait :
        
        - 📍 **Localisation** (Mat et numéro de fight)
        - 🕐 **Horaire** du match
        - 🥋 **Noms des combattants** et leurs clubs
        - 🔢 **Numéros** des compétiteurs
        
        **Types de matchs détectés :**
        - ✅ Matchs avec au moins 1 combattant confirmé
        - 🟠 Inclut les matchs avec "Winner of Fight X"
        - ❌ Matchs uniquement "Winner vs Winner" ignorés
        - ❌ Matchs avec BYE ignorés
        """)
    
    st.markdown("---")
    st.subheader("📊 Données globales des matchs importés")


    if 'last_update_time' not in st.session_state:
        st.session_state['last_update_time'] = time.time()
    elif time.time() - st.session_state['last_update_time'] > 300:
        update_from_all_urls()
        st.session_state['last_update_time'] = time.time()


    if 'global_df' in st.session_state and not st.session_state['global_df'].empty:
        st.dataframe(st.session_state['global_df'].sort_values(by='Numero'), use_container_width=True)
    else:
        st.info("Aucune donnée globale à afficher.")


if __name__ == "__main__":
    main()