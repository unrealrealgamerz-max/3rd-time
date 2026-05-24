const fs = require('fs');
const https = require('https');

// This is an open, public RSS feed of freshly updated indie and arcade games
const FEED_URL = 'https://itch.io/games/newest.xml'; 
const JSON_FILE = 'games.json';

// Simple helper to download the text data from the game feed
function fetchFeed(url) {
    return new Promise((resolve, reject) => {
        https.get(url, { headers: { 'User-Agent': 'Mozilla/5.0' } }, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => resolve(data));
        }).on('error', reject);
    });
}

async function startAutomation() {
    try {
        console.log("Fetching latest games from feed...");
        const xmlData = await fetchFeed(FEED_URL);
        
        // Simple regex patterns to pull Titles, Links, and Images out of the XML text feed
        const items = xmlData.split('<item>').slice(1);
        let currentGames = [];

        // Try to read your existing games list so we don't erase old ones
        if (fs.existsSync(JSON_FILE)) {
            try {
                currentGames = JSON.parse(fs.readFileSync(JSON_FILE, 'utf8'));
            } catch (e) {
                currentGames = [];
            }
        }

        let addedCount = 0;

        for (let item of items) {
            const titleMatch = item.match(/<title><!\[CDATA\[(.*?)\]\]><\/title>/) || item.match(/<title>(.*?)<\/title>/);
            const linkMatch = item.match(/<link>(.*?)<\/link>/);
            const imgMatch = item.match(/<enclosure[^>]*url="(.*?)"/) || item.match(/<media:content[^>]*url="(.*?)"/);
            
            if (titleMatch && linkMatch) {
                const title = titleMatch[1].trim();
                const link = linkMatch[1].trim();
                const image = imgMatch ? imgMatch[1] : 'https://via.placeholder.com/300x400?text=No+Preview';
                
                // Check if this game is already on our website list
                const alreadyExists = currentGames.some(g => g.title === title);
                
                if (!alreadyExists && addedCount < 5) {
                    // Create a clean new card match for your layout
                    const newGameCard = {
                        title: title,
                        version: "v1.0 New",
                        category: "Arcade",
                        image_url: image,
                        download_url: link
                    };
                    
                    // Put the newest game at the very top of the list
                    currentGames.unshift(newGameCard);
                    addedCount++;
                }
            }
        }

        // Save the updated list back to your games.json file
        fs.writeFileSync(JSON_FILE, JSON.stringify(currentGames, null, 2), 'utf8');
        console.log(`Successfully added ${addedCount} brand new games to lustarcade!`);

    } catch (error) {
        console.error("Automation error:", error.message);
    }
}

startAutomation();
