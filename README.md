# Showtimes Backend

This repository contains the code for the backend API that are used on the bot and also the WebUI.

The reason this was made is as an improvement to the current system and also as my final year project since naoTimes always started as a solo project by @noaione

## Why?
I created this project back in 2019 as Indonesian equivalent version of existing or similar project. I don't see their code, I only do what I think looks correct and now I'm basically botching together my bot and WebUI which honestly, a really bad design.

This project mainly aims to decouple the Showtimes module from the Bot to it's own thing, complete with more "big data" stuff like performance analytics and more! This is only a backend part of the project which only contains the API code made using GraphQL. See the [WebUI](https://github.com/noaione/naoTimesUI) implementations or the [Discord Bot](https://github.com/naoTimesdev/naoTimes) for a "frontend" view of it.

Another reason, both of my WebUI and Discord Bot actually has their own database connection and handle *their* own data differently for Showtimes which is bad. This project also aims to unify the data handling to make sure we only need one single handler that can be used repeatedly without we forgetting to change the other handler.

## Requirements
TO BE WRITTEN

## Running
TO BE WRITTEN

## Acknowledgments
- [Aquarius](https://github.com/IanMitchell/aquarius), the original idea for this project.
- [Anilist](https://anilist.co/), API source for Japanese related media.
- [TMDB](https://www.themoviedb.org/), API source for mainly non-Japanese media.
- And, all of my small project I created before since I'm reusing some of the code :D

## License

This project is licensed with [AGPL 3.0](https://github.com/naoTimesdev/showtimes) under a pseudo-nyms, please refer to the University paper for real name used for this project.

Anyone is free to use and redistribute this project and make sure to link back to the original project. More info: [GNU Affero General Public License v3](https://tldrlegal.com/license/gnu-affero-general-public-license-v3-(agpl-3.0))