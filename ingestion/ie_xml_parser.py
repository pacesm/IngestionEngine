############################################################
#  Project: DREAM
#  Module:  Task 5 ODA Ingestion Engine 
#  Author: Milan Novacek (CVC)
#  Date:   Sept 16, 2013
#
#    (c) 2013 Siemens Convergence Creators s.r.o., Prague
#    Licensed under the 'DREAM ODA Ingestion Engine Open License'
#     (see the file 'LICENSE' in the top-level directory)
#
#  Ingestion Engine: xml and  metadata parser utility
#
############################################################

import logging
import xml.etree.ElementTree as ET
import xml.parsers.expat

from settings import IE_DEBUG

from utils import \
    bbox_to_WGS84, \
    Bbox, \
    bbox_from_strings, \
    TimePeriod, \
    NoEPSGCodeError, \
    IngestionError

# namespaces
wcs_vers = '2.0'
WCS_NS   = '{http://www.opengis.net/wcs/' + wcs_vers + '}'
WCSEO_NS = '{http://www.opengis.net/wcseo/1.0}'
OWS_NS   = '{http://www.opengis.net/ows/2.0}'
GML_NS   = '{http://www.opengis.net/gml/3.2}'
GMLCOV_NS= '{http://www.opengis.net/gmlcov/1.0}'
EOP_NS   = '{http://www.opengis.net/eop/2.0}'
OM_NS    = '{http://www.opengis.net/om/2.0}'
OPT_NS   = '{http://www.opengis.net/opt/2.0}' 

EXCEPTION_TAG      = "ExceptionReport"
DEFAULT_SERVICE_VERSION = "2.0.1"

#<gml:boundedBy>
#<gml:Envelope axisLabels="lat long" 
#   srsDimension="2" srsName="http://www.opengis.net/def/crs/EPSG/0/4326" 
#   uomLabels="deg deg">
#   <gml:lowerCorner>44.14 0.8</gml:lowerCorner>
#   <gml:upperCorner>44.15 0.9</gml:upperCorner>
# </gml:Envelope></gml:boundedBy>

# <gmlcov:metadata>
#   <gmlcov:Extension>
#     <wcseo:EOMetadata>
#       <eop:EarthObservation
#            gml:id="eop_L930564_20110119_L5_199_030_USGS_surf_pente_30m_RGB_WSG84"
#            xsi:schemaLocation="http://www.opengis.net/opt/2.0 ../xsd/opt.xsd">
#         <om:phenomenonTime>
#           <gml:TimePeriod
#             gml:id="tp_L930564_20110119_L5_199_030_USGS_surf_pente_30m_RGB_WSG84">
#               <gml:beginPosition>2011-01-19T00:00:00</gml:beginPosition>
#               <gml:endPosition>2011-01-19T00:00:00</gml:endPosition>
#           </gml:TimePeriod>
#         </om:phenomenonTime>

# <gmlcov:Extension>
#   <wcseo:EOMetadata>
#   <eop:EarthObservation
#       gml:id="eop_L930564_20110119_L5_199_030_USGS_surf_pente_30m_RGB_WSG84"
#       xsi:schemaLocation="http://www.opengis.net/opt/2.0 ../xsd/opt.xsd">
#     <eop:metaDataProperty>
#       <eop:EarthObservationMetaData>
#         <eop:identifier>L930564_20110119_L5_199_030_USGS_surf_pente_30m_RGB_WSG84</eop:identifier>
#       </eop:EarthObservationMetaData>
#     </eop:metaDataProperty>
#   </eop:EarthObservation>

EO_METADATA_XPATH = \
    GMLCOV_NS + "metadata/" + \
    GMLCOV_NS + "Extension/" + \
    WCSEO_NS  + "EOMetadata/"

EO_PHENOMENONTIME = \
    EO_METADATA_XPATH + \
    EOP_NS+"EarthObservation/" + \
    OM_NS+"phenomenonTime"

EO_IDENTIFIER_XPATH = \
    EO_METADATA_XPATH + \
    EOP_NS+"EarthObservation/" + \
    EOP_NS+"metaDataProperty/" + \
    EOP_NS+"EarthObservationMetaData/" + \
    EOP_NS+"identifier/"

EO_EQUIPMENT_XPATH = \
    EO_METADATA_XPATH + \
    EOP_NS   + "EarthObservation/" + \
    OM_NS    + "procedure/"        + \
    EOP_NS   + "EarthObservationEquipment/"

# cloud cover XML example
# <!-- cloud cover -->
# <gmlcov:metadata>
#   <gmlcov:Extension>
#     <wcseo:EOMetadata>
#       <eop:EarthObservation gml:id="b57ea609-">
#         <om:result>
#           <opt:EarthObservationResult gml:id="uuid_94567f">
#             <opt:cloudCoverPercentage uom="%">13.25</opt:cloudCoverPercentage>
#           </opt:EarthObservationResult>
#         </om:result>
#       </eop:EarthObservation>
#     </wcseo:EOMetadata>
#   </gmlcov:Extension>
# </gmlcov:metadata>

CLOUDCOVER_XPATH = \
    EO_METADATA_XPATH + \
    EOP_NS   + "EarthObservation/" + \
    OM_NS    + "result/"           + \
    OPT_NS   + "EarthObservationResult/" + \
    OPT_NS   + "cloudCoverPercentage"
    

# sensor type XML example:
# <gmlcov:metadata>
#   <gmlcov:Extension>
#     <wcseo:EOMetadata>
#       <eop:EarthObservation gml:id="some_id"
#        xsi:schemaLocation="http://www.opengis.net/opt/2.0 ../xsd/opt.xsd">
#         <om:procedure>
#           <eop:EarthObservationEquipment gml:id="some_id">  
#             <eop:sensor>
#               <eop:Sensor>
#                 <eop:sensorType>OPTICAL</eop:sensorType>
#               </eop:Sensor>
#             </eop:sensor>
#           </eop:EarthObservationEquipment>
#         </om:procedure>
#
SENSOR_XPATH = \
    EO_EQUIPMENT_XPATH +\
    EOP_NS   + "sensor/" + \
    EOP_NS   + "Sensor/" + \
    EOP_NS   + "sensorType"
    
# acquisition angle XML example
# <!-- acquisition angle -->
# <gmlcov:metadata>
#   <gmlcov:Extension>
#     <wcseo:EOMetadata>
#
#       <eop:EarthObservation gml:id="some_id" >
#         <om:procedure>
#           <eop:EarthObservationEquipment gml:id="some_id">
#             <eop:acquisitionParameters>
#               <eop:Acquisition>
#                 <eop:incidenceAngle uom="deg">+7.23391641</eop:incidenceAngle>
#               </eop:Acquisition>
#             </eop:acquisitionParameters>
#           </eop:EarthObservationEquipment>
#         </om:procedure>
#       </eop:EarthObservation>

INCIDENCEANGLE_XPATH = \
    EO_EQUIPMENT_XPATH  + \
    EOP_NS   + "acquisitionParameters/" + \
    EOP_NS   + "Acquisition/" + \
    EOP_NS   + "incidenceAngle"


logger = logging.getLogger('dream.file_logger')


# ------------ XML metadata parsing --------------------------

def get_coverageDescriptions(cd_tree):
    return cd_tree.findall("./" + \
                               WCS_NS + "CoverageDescriptions" + "/" +\
                               WCS_NS + "CoverageDescription")

def srsName_to_Number(srsName):
    if not srsName.startswith("http://www.opengis.net/def/crs/EPSG"):
        raise NoEPSGCodeError("Unknown SRS: '" + srsName +"'")
    return int(srsName.split('/')[-1])

def is_nc_tag(qtag, nctag):
    parts=qtag.split("}")
    if len(parts)==1:
        return qtag==nctag
    elif len(parts)==2:
        return nctag==parts[1]
    else:
        return False

def tree_is_exception(tree):
    return is_nc_tag(tree.tag, EXCEPTION_TAG)


def extract_path_text(cd, path):
    ret = None
    leaf_node = cd.find("./"+path)
    if None == leaf_node:
        return None
    return leaf_node.text


def extract_eoid(cd):
    return extract_path_text(cd, EO_IDENTIFIER_XPATH)


def extract_Id(dss):
    dsid = dss.find("./"+ WCSEO_NS + "DatasetSeriesId")
    if None == dsid:
        logger.error("'DatasetSeriesId' not found in DatasetSeriesSummary")
        return None
    return dsid.text


def is_x_axis_first(axisLabels):
    labels = axisLabels.strip().lower().split(' ')
    if len(labels) != 2:
        logger.error("Error: can't parse axisLabels '"+axisLabels+"'")
        return False
    if labels[0] == 'lat' or labels[0] == 'y':
        return False
    if labels[0] == 'long' or labels[0] == 'x':
        return True
    else:
        logger.error("Error: can't parse axisLabels '"+axisLabels+"'")
        return False

def extract_gml_bbox(cd):
    # cd is the CoverageDescription, should contain boundedBy/Envelope
    # The extracted bbox is converted to WGS84
    envelope = cd.find("./" + GML_NS + "boundedBy" + "/" \
                            +  GML_NS + "Envelope" )
    if None == envelope:
        return None

    srsNumber = None
    axisLabels = None
    try:
        axisLabels = envelope.attrib['axisLabels']
        srsName = envelope.attrib['srsName']
        srsNumber = srsName_to_Number(srsName)
    except KeyError:
        logger.error("Error: srsName or axisLabels not found")
        return None
    except NoEPSGCodeError as e:
        logger.error("Error: "+e)
        return None

    lc = envelope.find("./"+ GML_NS +"lowerCorner")
    uc = envelope.find("./"+ GML_NS +"upperCorner")

    if None==lc or None==uc:
        logger.error(
            "Error: lowerCorner or upperCorner not found in envelope.")
        return None

    bb = bbox_from_strings(lc.text, uc.text, is_x_axis_first(axisLabels))
    bbox_to_WGS84(srsNumber, bb)
    return bb


def extract_WGS84bbox(dss):
    WGS84bbox = dss.find("./"+ OWS_NS +"WGS84BoundingBox")
    if None == WGS84bbox:
        logger.error("'WGS84BoundingBox' not found in DatasetSeriesSummary")
        return None
    lc = WGS84bbox.find("./"+ OWS_NS +"LowerCorner")
    uc = WGS84bbox.find("./"+ OWS_NS +"UpperCorner")
    if None == lc or None == uc:
        logger.error("error, LowerCorner or Upper Corner not found in bbox")
        return None
    return bbox_from_strings(lc.text, uc.text)


def extract_TimePeriod(dss):
    # returns an instance of utils.TimePeriod
    tp = dss.find("./"+ GML_NS + "TimePeriod")
    if None == tp: return None
    begin_pos = tp.find("./"+ GML_NS + "beginPosition")
    end_pos   = tp.find("./"+ GML_NS + "endPosition")
    if None == begin_pos or None == end_pos: return None
    return TimePeriod(begin_pos.text, end_pos.text)

def extract_om_time(cd):
    phenomenonTime = cd.find("./" + EO_PHENOMENONTIME)
    if None==phenomenonTime:
        logger.error("Error: failed to find 'phenomenonTime'")
        return None
    return extract_TimePeriod(phenomenonTime)
    

def extract_ServiceTypeVersion(caps):
    stv = caps.findall("./"+ OWS_NS +"ServiceIdentification" +
                          "/" + OWS_NS +"ServiceTypeVersion")
    if len(stv) < 1:
        logger.warning("ServiceTypeVersion not found")
        return DEFAULT_SERVICE_VERSION
    return stv[0].text

def extract_DatasetSeriesSummaries(caps):
    result = []
    wcs_extension = caps.findall(
        "." +
        "/" + WCS_NS +"Contents" +
        "/" + WCS_NS + "Extension")
    if len(wcs_extension) < 1:
        logger.error("Contents/Extension not found")
    else:
        result = wcs_extension[0].findall(
        "./" + WCSEO_NS +"DatasetSeriesSummary")
    return result

def extract_CoverageId(cd):
    covId = None
    coverageIdNode = cd.find("./"+WCS_NS+"CoverageId")
    if None!=coverageIdNode:
        covId = coverageIdNode.text
    else:
        try:
            covId = cd.attrib[GML_NS+'id']
        except KeyError:
            pass
    return covId

def base_xml_parse(src_data):
    xml_root = ET.parse(src_data)
    return xml_root.getroot()

def parse_file(src_data, expected_root, src_name):
    result = None
    try:
        result = base_xml_parse(src_data)
        if None == result:
            raise IngestionError("No data")
        if tree_is_exception(result):
            result = None
            logger.warning("'"+src_name+"' contains exception")
            if IE_DEBUG > 0:
                logger.info(ET.tostring(result))
        elif expected_root and not is_nc_tag(result.tag, expected_root):
            msg = "'"+src_name+"' does not contain expected root '"+ \
                   `expected_root`, "'. In xml: "+`result.tag`
            logger.error(msg)
            result = None
    except IOError as e:
        loger.error("Cannot open/parse md source '"+src_name+"': " + `e`)
        return None
    except xml.parsers.expat.ExpatError as e:
        logger.error("Cannot parse '"+src_name+"', error="+`e`)
        return None
    except Exception as e:
        logger.error("Cannot parse '"+src_name+"', unknown error:" + `e`)
        return None

    return result

