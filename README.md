**Books Website Scraping**

Setup instructions:

1) Download the github repo using the command below or manually:  
* git clone https://github.com/username/repository-name.git  
2) Download & Install the python dependencies using the command:  
* pip install \-r requirements.txt  
3) Use the command below to crawl the website:  
* python \-m crawler.crawler   
4) Use the command below to start the schedular:  
* python \-m scheduler.scheduler  
5) To run the apis, start the server with the command:  
* uvicorn api.main:app \--reload  
6) To run the tests, run the command:  
* pytest \-v

Python version: 3.13.3

Dependency versions:

* aiohappyeyeballs==2.6.1  
* aiohttp==3.13.2  
* aiosignal==1.4.0  
* annotated-doc==0.0.4  
* annotated-types==0.7.0  
* anyio==4.11.0  
* APScheduler==3.11.1  
* attrs==25.4.0  
* beautifulsoup4==4.14.2  
* certifi==2025.11.12  
* click==8.3.1  
* colorama==0.4.6  
* Deprecated==1.3.1  
* dnspython==2.8.0  
* fastapi==0.122.0  
* fastapi-pagination==0.15.0  
* frozenlist==1.8.0  
* h11==0.16.0  
* httpcore==1.0.9  
* httptools==0.7.1  
* httpx==0.28.1  
* idna==3.11  
* iniconfig==2.3.0  
* limits==5.6.0  
* lxml==6.0.2  
* motor==3.7.1  
* multidict==6.7.0  
* numpy==2.3.5  
* packaging==25.0  
* pandas==2.3.3  
* pluggy==1.6.0  
* propcache==0.4.1  
* pydantic==2.12.5  
* pydantic\_core==2.41.5  
* Pygments==2.19.2  
* pymongo==4.15.4  
* pytest==9.0.1  
* pytest-asyncio==1.3.0  
* python-dateutil==2.9.0.post0  
* python-dotenv==1.2.1  
* pytz==2025.2  
* PyYAML==6.0.3  
* six==1.17.0  
* slowapi==0.1.9  
* sniffio==1.3.1  
* soupsieve==2.8  
* starlette==0.50.0  
* tenacity==9.1.2  
* typing-inspection==0.4.2  
* typing\_extensions==4.15.0  
* tzdata==2025.2  
* tzlocal==5.3.1  
* uvicorn==0.38.0  
* watchfiles==1.1.1  
* websockets==15.0.1  
* wrapt==2.0.1  
* yarl==1.22.0

Example .env file for config:

* MONGO\_URI=mongodb://localhost:27017  
* MONGO\_DB=web\_scraping  
* API\_KEY=testapikey  
* API\_PORT=8000  
* SMTP\_HOST=smtp.gmail.com  
* SMTP\_PORT=587  
* SMTP\_USER=your\_email\_address  
* SMTP\_PASS=SMTP\_password\_from\_google\_account  
* ALERT\_EMAIL=target\_email\_address  
* FROM\_EMAIL=your\_email\_address  
* REPORT\_DIR="./reports"  
* BASE\_URL="https://books.toscrape.com"  
* CRAWL\_CONCURRENCY=10  
* CRAWL\_RETRIES=3