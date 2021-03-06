IngestionEngine
===============

DREAM Ingestion Engine

This is release 0.5.1.
Basic ingestion functionality should work.
Includes sample scenarios for testing; it is suggested to use the
last one ('cc_and_incidence') for a first test.

### Update 19.1.2014:

* enabled usage with the ODA Client Ingestion Admin T5. The Ingestion Engine
  may now be used either with its lightweight standalone development client,
  or with the main ODA Client (`https://github.com/DREAM-ODA-OS/ODAClient`)

* for other updates see Other Updates towards the bottom of the page

## Installation and Configuration

### Notes
0. The s/w uses the DREAM-adaptation of the ngEO_Download_Manager
    for getting the products from the product facilities. 

### Prerequisites

The DREAM ngEO-download-manager is assumed to be installed.  
Other key packages are listed in the `requirements.txt` file; use `pip` to
install these if you don't have them.

### Installation and Configuration
0. Download the IngestionEngine, e.g. to a directory `oda/ing`
0. possibly run `./manage.py collectstatic`
0.  The top-level Ingestion Engine directory (`ing` in our example) 
contains the main config file `ingestion_config.json`.
It is mandatory to set the path
for `DownloadManagerDir`; this is the location of the DM's home dir
(from there the Ingestion Engine finds the Download Managers `config`
directory).  A relative path given here is taken relative to the
Ingestion Engine's top-level directory, i.e. the one where 'manage.py'
is located.  Most of the time you'll be safer to set an absolute path
there.  A path starting with `../` is also fine.
The DownloadDirectory is created if it does not exist as long as its
parent directory exists (i.e. a full recursive path is not created).
If you should require more fine-tuning then
edit the variables in `settings.py` or in `dm_control.py`. 
0. The `ie_server_port` in  `ingestion_config.json` should also be set
to the same port that will be used to run the django server with (or
where the ingestion engine will listen on), but note that the code
only uses this to easily find out where it is listening, and by itself
setting `ie_server_port` will not ensure that the ingestion engine is
indeed listening there.
0. Make sure the Download Manger(DM) is configured correctly: 
The config is in
`ngEO-download-manager/conf/userModifiableSettingsPersistentStore.properties`.
Ensure that `WEB_INTERFACE_PORT_NO` and
`BASE_DOWNLOAD_FOLDER_ABSOLUTE` are set-up correctly.
If you change these then re-start the DM. This is important because
the IE reads these settings from the DM's config dir, and the IE
needs the same values as the _running_ DM.
0. If you're using 'ODA Client Ingestion Admin T5', then be sure
to configure in the ODA Client the property `ingestionEngineT5.baseUrl`,
in the file `ODAClient/app/config.json` of the ODA Client installation tree.

### Launching
0. It is assumed the DM is either already running or will be started
more or less concurrently with the IE; the IE will wait some time
(configurable) for the DM to be available.
0. For testing, start the Ingestion Engine via the suplied script 'ie'; it
will check to see if initialization is needed and then run django's development server.
Note the dev server should not be used for production or for pages publicly accessible
from the Internet.

    ```
    cd oda/iedir
    ./ie [port]
    ```
_port_ is optional and specifies where the ingestion engine is listening.
As a django application the default is 8000.

`ie` is a script that runs `./manage.py syncdb` if needed (e.g. on first time
startup) to ininialise the Ingestion Engine's database and to pre-load a 
test-scenario.  Then it runs `./manage.py runserver`
If the DM is also running, then a successfuly completed start-up of the IE is
indicated by the following line being logged to the logfile and to stdout:

    ```
    DM Port OK, waited 22.2 secs.
    ```

0. (optional) To use the standalone development client, simply view the
   Ingestion Admin Client page in a browser:
    `http://127.0.0.1:8000/ingestion`.
   This is a lightweight developement client, and it is recommended to use only
   one instance of the this client, and not to use anther client concurrently
   (like the ODA Client described below).
   The client can be configured to run without access to the internet.

0. Instead of the standalone development client described in the above
   step use the ODA Client Ingestion Admin T5.
   see `https://github.com/DREAM-ODA-OS/ODAClient`

0. To shut down the dev server, use `^C`.

## License

See the LICENSE for licensing conditions, it is a MIT-style open
source license.

### Other updates

*  (16.12.) The interface IF-DREAM-O-UpdateQualityMD is operational up
to (including)  executing the ODA-Server update script
`ingestion/media/scripts/def_uqmd.sh`, which is an intenal inteface
to the ODA Server.  See the script for details on this internal IF.

*  (16.12.) The test script `test/updateQualityMD_sa/test_uqmd.py`
serves as an example of how to use the IF-DREAM-O-UpdateQualityMD interface.

*   (16.12.) The interface IF-DREAM-O-AddProduct is operational up
to (including)  executing the ODA-Server update script
`ingestion/media/scripts/def_addProduct.sh`, which is an intenal inteface
to the ODA Server. See the script for details on this internal IF.
The inteface IF-DREAM-O-AddProduct comprises two operations: 
`addProduct` and `getStatus`.
An example of how to use these is shown in the test script for this
interface: `test/addProduct_sa/test_addProd.py`

*  (03.12.) The interface to the ngEO Download Manager (v 0.5.4) is operational.

*  (03.12.) The IE+DM can download products from product facilities that use EO-WCS.
Registering products in the ODA server remains
to be tested; the IE executes the registation shell script
`ingestion/media/scripts/def_ingest.sh`
For development and debugging only the first 4 download URLs generated
for a given scenario are downloaded.

* (03.12.) A test-scnenario is pre-loaded on first start-up, see the
installation instructions.

