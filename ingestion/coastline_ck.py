############################################################
#  Project: DREAM
#
#  Module:  Task 5 ODA Ingestion Engine 
#
#  Author: Milan Novacek (CVC)
#
#  Date:   Jan 9, 2014
#
#    (c) 2014 Siemens Convergence Creators s.r.o., Prague
#    Licensed under the 'DREAM ODA Ingestion Engine Open License'
#     (see the file 'LICENSE' in the top-level directory)
#
#  Ingestion Engine: Perform Coastline Check
#   The main function checks if the area described in the metadata 
#   is within the coastline polygon.
#   There is also a function 'coastline_cache_from_aoi' used to 
#   setup the polygon(s) within an AOI. The output of this is used
#   in the coastline check proper.
#
#  used by ingestion_logic
#
############################################################

import logging
import json
import os.path
import traceback

#debugging support
have_tk = False
tk_root = None
grdbg   = None
LOCAL_DEBUG = False

class Grdbg:
    CANVAS_W = 1024
    CANVAS_H =  768
    x_offset = 0.0
    y_offset = 0.0
    scale = 1.0

    _minx = 0.0
    _maxx = CANVAS_H
    _miny = 0.0
    _maxy = CANVAS_W

    def __init__(self, master):

        frame = Tk.Frame(master)
        frame.pack()

        self.button = Tk.Button(frame, text="QUIT", fg="red", command=frame.quit )
        self.button.pack(side=Tk.LEFT)

        self.canvas = Tk.Canvas(master, width=self.CANVAS_W, height=self.CANVAS_H)
        self.canvas.pack(side=Tk.LEFT)


    def add_line(self, x1, y1, x2, y2, color=None):

        x1 =                  (x1+self.x_offset) * self.scale
        y1 = self.CANVAS_H - ((y1+self.y_offset) * self.scale)
        x2 =                  (x2+self.x_offset) * self.scale
        y2 = self.CANVAS_H - ((y2+self.y_offset) * self.scale)
        if None == color:
            self.canvas.create_line(x1, y1, x2, y2)
        else:
            self.canvas.create_line(x1, y1, x2, y2, fill=color)


    def reset_xform(self, minX, maxX, minY, maxY):

        is_adjusted = False
        adj_minx = self._minx
        adj_miny = self._miny
        adj_maxx = self._maxx
        adj_maxy = self._maxy

        if minX < self._minx:
            adj_minx = minX
            is_adjusted = True

        if minY < self._miny:
            adj_miny = minY
            is_adjusted = True

        if maxX > self._maxx:
            adj_maxx = maxX
            is_adjusted = True

        if maxY > self._maxy:
            adj_maxy = maxY
            is_adjusted = True

        if is_adjusted:
            self.set_xform(adj_minx, adj_maxx, adj_miny, adj_maxy)


    def set_xform(self, minX, maxX, minY, maxY):

        print " setting xform for ( (" + \
            `minX` + " " + \
            `minY` + "), (" + \
            `maxX` + " " + \
            `maxY` + ") )"

        self._minx = minX
        self._maxx = maxX
        self._miny = minY
        self._maxy = maxY

        x_extent = abs(maxX - minX)
        if x_extent < 0.01: x_extent = 0.5
        else: x_extent *= 1.05
        x_scale = float(self.CANVAS_W) / x_extent

        y_extent = abs(maxY - minY)
        if y_extent < 0.01: y_extent = 0.5
        else: y_extent *= 1.05
        y_scale = float(self.CANVAS_H) / y_extent

        if x_scale > y_scale :
            self.scale = y_scale
        else:
            self.scale = x_scale

        self.x_offset = (0.025*x_extent) - minX
        self.y_offset = (0.025*y_extent) - minY

        print "x_off: "  + `self.x_offset`
        print "y_off: "  + `self.y_offset`
        print "scale: "  + `self.scale`


if LOCAL_DEBUG or __name__ == '__main__':
    try:
        import Tkinter as Tk
        have_tk = True
    except Exception as e1:
        try:
            import tkinter as Tk
            have_tk = True
        except Exception as e2:
            print `e1`
            print `e2`
            print "\n *** No Tkinter nor tkinter - graphical debug is disabled ***\n"
    if have_tk:
        tk_root = Tk.Tk()
        grdbg = Grdbg(tk_root)

if __name__ == '__main__':
    # Enable stand-alone testing without django
    IE_DEBUG = 1
    from utils import DummyLogger
    logger = DummyLogger()

else:
    from settings import \
        IE_DEBUG
    logger = logging.getLogger('dream.file_logger')


from utils import \
    IngestionError, \
    Bbox

from ie_xml_parser import extract_footprintpolys


is_ie_c_check = False
shp_driver = None
mem_driver = None

try:
    import osgeo.gdal as gdal
    import osgeo.ogr as ogr
    import osgeo.osr as osr
    shp_driver = ogr.GetDriverByName('ESRI Shapefile')
    mem_driver = ogr.GetDriverByName('Memory')
    is_ie_c_check = True
except Exception as e:
    logger.error("ERROR: cannot import/initialise osgeo/ogr; coastline check will fail")
    is_ie_c_check = False

#--------------------------------------------------------------------
# Create an ogr polygon from the data in the Coverage Desr.
# In the cov. descr, the order of coordinate points is N, E
# The returned OGR geometry points have the order x,y (E,N).
#
def extract_geom(coverageDescription, cid, wcs_type):
   
    coords = extract_footprintpolys(coverageDescription, wcs_type)
    if not coords or len(coords) == 0:
        logger.warning("No polygon in coverageDescription for "+`cid`+
                       ' - not checking coastline.')
        return None

    ring = ogr.Geometry(ogr.wkbLinearRing)
    for xy in coords:
        ring.AddPoint(xy[1], xy[0])
    coverage_ftprint = ogr.Geometry(ogr.wkbPolygon)
    coverage_ftprint.AddGeometry(ring)
    if IE_DEBUG > 2:
        logger.debug("    cd_ftprint.env: " + `coverage_ftprint.GetEnvelope()`)

    return coverage_ftprint

#--------------------------------------------------------------------
# Check if the polygon contained in the coverageDescription
# intesects with or is within the ccache polygon.
#
def coastline_ck(coverageDescription, cid, ccache, wcs_type):
    if not ccache:
        logger.warning('No coastline cache - not checking.')
        return True

    if IE_DEBUG > 0:
        logger.info('  performing coastline_check')

    # create an ogr polygon from the data in the Coverage Description
    coverage_ftprint = extract_geom(coverageDescription, cid, wcs_type)

    if IE_DEBUG > 2:
        logger.debug("    coastline_ck(): coverage_ftprint.env: " + `coverage_ftprint.GetEnvelope()`)
        #print_geom(coverage_ftprint)

    cclayer = ccache.GetLayer()
    if None == cclayer:
        return True

    cclayer.ResetReading()
    feature = cclayer.GetNextFeature()
    if not feature:
        logger.warning("coastline_ck: NO FEATURE in coastline cache layer. Not checking.")
        return True

    checking = False
    intersects = False
    while feature:
        geom = feature.GetGeometryRef()
        if not geom:
            logger.warning("coastline_ck: NO GEOM!")
        else:

            geom_count = geom.GetGeometryCount()
            if IE_DEBUG > 2:
                logger.debug(" check "+`geom.GetGeometryName()`+
                             ", geom count="+`geom_count`)
                        
            for i in range(geom_count):
                checking = True
                poly = geom.GetGeometryRef(i)
                if IE_DEBUG > 2:
                    logger.debug("    env:" + `poly.GetEnvelope()`)
                    #print_poly(poly)
                if poly.Intersects(coverage_ftprint) or \
                        poly.Contains(coverage_ftprint) or \
                        coverage_ftprint.Contains(poly):
                    intersects = True
                    if IE_DEBUG > 2:
                        logger.debug("    ...intersects.")
                    break;

        feature = cclayer.GetNextFeature()

    cclayer.ResetReading()
    if IE_DEBUG > 0 and not checking:
        logger.debug("  Coastline was empty - automatic fail.")

    if IE_DEBUG > 0:
        if not intersects:
            logger.debug("  coastline check failed.")
            
    return intersects


#--------------------------------------------------------------------
# Create an OGR layer with the clipped polygon data.
#
def create_clipped_layer(src_layer, aoi, ogr_bbox, shpfile):

    #src_layer.SetSpatialFilter(ogr_bbox)

    feature = src_layer.GetNextFeature()
    if not feature:
        logger.error("Error getting any features from " + shpfile)
        raise IngestionError("Error initialising 30km-coastline.")

    # create new layer
    clipped_source = mem_driver.CreateDataSource("tmp_coastline")
    clipped_layer = clipped_source.CreateLayer(
        "clipped_layer", geom_type=ogr.wkbMultiPolygon)
    clipped_multipoly = ogr.Geometry(ogr.wkbGeometryCollection)
    wgs84srs = osr.SpatialReference()
    wgs84srs.ImportFromEPSG(4326)
    clipped_multipoly.AssignSpatialReference(wgs84srs)

    if LOCAL_DEBUG:
        print " LOCAL-- aoi: "+`aoi`

    total_vertices = 0
    while feature:
        geom = feature.GetGeometryRef()
        count = geom.GetGeometryCount()

        for i in range(count):
            poly = geom.GetGeometryRef(i)

            #first get rid of all polys completely outside our AOI
            # env returns (minN,maxN, minE,maxE)
            envelope = poly.GetEnvelope()

            if envelope[0] > aoi.ur[0] or envelope[1] < aoi.ll[0]: continue
            if envelope[2] > aoi.ur[1] or envelope[3] < aoi.ll[1]: continue

            debug_clip = False
            #if i == 3895:  debug_clip = True

            # clip those that remain.
            clipped_vertices = clip_poly(aoi, poly, debug_clip)

            total_vertices += len(clipped_vertices)
            if debug_clip:
                print "     n clipped_vertices : " + `len(clipped_vertices)`
                if 0 != len(clipped_vertices):
                    print "v0: "+`clipped_vertices[0]`+ \
                        ",  v1:"+`clipped_vertices[-1]`
            clipped_poly = ogrPolyFromVertices(clipped_vertices)
            clipped_multipoly.AddGeometry(clipped_poly)

        feature.Destroy()
        feature = src_layer.GetNextFeature()

    clipped_feature_def = clipped_layer.GetLayerDefn()
    clipped_feature  = ogr.Feature(clipped_feature_def)
    clipped_feature.SetGeometry(clipped_multipoly)
    clipped_layer.CreateFeature(clipped_feature)

    if IE_DEBUG > 0 and 0 == total_vertices:
        logger.warning("Created Empty Coastline Cache.")

    return clipped_source

def coastline_cache_from_aoi(shpfile, prjfile, aoi):

    if not is_ie_c_check:
        logger.error("Coastline check is not enabled:"+
                     " could not import osgeo.")
        raise IngestionError("Coastline check failed prerequisites.")

    if None != prjfile:
        logger.error("Only WGS84 is supported for coastline check geometry")

    if IE_DEBUG > 0:
        logger.debug('Calculating clipped_coastline_from_aoi ' + `aoi`)

    src_data_source = shp_driver.Open(shpfile, 0)
    if None == src_data_source:
        logger.error("OGR cannot read " + shpfile)
        raise IngestionError("Error initialising 30km-coastline.")

    src_layer = src_data_source.GetLayer()
    if None == src_layer:
        logger.error("Error getting layer from " + shpfile)
        raise IngestionError("Error initialising 30km-coastline.")

    # create new layer
    res_data_source = mem_driver.CreateDataSource("tmp_coastline")
    out_layer = res_data_source.CreateLayer(
        "coast_layer", geom_type=ogr.wkbMultiPolygon)
    out_multipoly = ogr.Geometry(ogr.wkbGeometryCollection)
    wgs84srs = osr.SpatialReference()
    wgs84srs.ImportFromEPSG(4326)
    out_multipoly.AssignSpatialReference(wgs84srs)

    # create AOI bbox as an ogr polygon
    ring = ogr.Geometry(ogr.wkbLinearRing)
    ring.AddPoint(aoi.ll[0], aoi.ll[1])
    ring.AddPoint(aoi.ll[0], aoi.ur[1])
    ring.AddPoint(aoi.ur[0], aoi.ur[1])
    ring.AddPoint(aoi.ur[0], aoi.ll[1])
    ring.AddPoint(aoi.ll[0], aoi.ll[1])

    ogr_bbox = ogr.Geometry(ogr.wkbPolygon)
    ogr_bbox.AddGeometry(ring)

    clipped_src = create_clipped_layer(src_layer, aoi, ogr_bbox, shpfile)
    clipped_layer = clipped_src.GetLayer()

    feature = clipped_layer.GetNextFeature()
    if not feature:
        logger.warning("Clipping coastline to AOI results in empty set.")

    while feature:
        geom = feature.GetGeometryRef()
        count = geom.GetGeometryCount()
        n_rejected = 0
        n_inside = 0
        n_intesects = 0
        n_bb_contains = 0

        for i in range(count):
            keep = False
            poly = geom.GetGeometryRef(i)

            if poly.Contains(ogr_bbox):
                n_inside += 1
                keep = True

            #if points_coincide(aoi, poly) or poly.Intersects(ogr_bbox):
            if not keep and poly.Intersects(ogr_bbox):
                n_intesects += 1
                keep = True

            if not keep and ogr_bbox.Contains(poly):
                n_bb_contains += 1
                keep = True

            if keep:
                cloned = poly.Clone()
                err = out_multipoly.AddGeometry(cloned)
                if err != 0:
                    logger.error(
                        "Internal Error construcing geom-cache, e="+ err)
                    raise IngestionError("Error initialising 30km-coastline.")
            else:
                n_rejected  += 1

        feature.Destroy()
        if IE_DEBUG > 1:
            logger.debug(
                "Cache coastline subset: " +
                "n rejected/inside/intersects/contains: " +
                `n_rejected`   + " / " +
                `n_inside`     + " / " +
                `n_intesects`  + " / " +
                `n_bb_contains`)
        feature = src_layer.GetNextFeature()
 
    src_layer = None
    src_data_source.Destroy()

    out_feature_def = out_layer.GetLayerDefn()
    out_feature  = ogr.Feature(out_feature_def)
    out_feature.SetGeometry(out_multipoly)
    out_layer.CreateFeature(out_feature)

    return res_data_source


#####################################################################
# ---------------------------- clipping -----------------------------
#####################################################################
#
NEARZEROTOL = 2.0e-9

# ------------ Intersection  --------------------------
class Isection:
    # Members:
    #  - point, consists of an (N,E) pair
    #  - is_on_bound, a Boolean. True if the intersection point is
    #                 on the boundary box, False if on one of the
    #                 infinite constant-x or constant-y lines but beyond
    #                 the lower left and uppper-right corners of the bb.
    def __init__(self, pt, is_on_bound):
        self.pt = pt
        self.is_on_bound = is_on_bound

    def __str__(self):
        return "("+`self.pt[0]` +","+ `self.pt[1]`+"): "+ `self.is_on_bound`

    def __repr__(self):
        return "("+`self.pt[0]` +","+ `self.pt[1]`+"): "+ `self.is_on_bound`



#--------------------------------------------------------------------
# Create an OGR polygon from a list of vertices
#
def ogrPolyFromVertices(vertices, is_x_first=True):

    ring = ogr.Geometry(ogr.wkbLinearRing)

    if is_x_first:
        for v in vertices:
            ring.AddPoint(v[0], v[1])
    else:
        for v in vertices:
            ring.AddPoint(v[1], v[0])
        
    poly = ogr.Geometry(ogr.wkbPolygon)
    poly.AddGeometry(ring)

    return poly


#--------------------------------------------------------------------
# Determine if a point pt is inside a bbox
#
def is_pt_in_BB(bb, pt):
    minN = bb.ll[1]
    maxN = bb.ur[1]
    minE = bb.ll[0]
    maxE = bb.ur[0]
    return \
        pt[0] >= minE and pt[0] <= maxE and \
        pt[1] >= minN and pt[1] <= maxN 


#--------------------------------------------------------------------
# Calculate the x (E) coordinate corresponding to northing Ni on
#  the line segment (p0,p1)
# Points format is (E, N)
# Assumes an intersection does exist,
#   i.e. y0 < Ni < y1  or y1 < Ni < y0
#
def calc_xi(p0, p1, Ni):

    # x is Easting, y is Northing.
    # Points format is (E, N)
    dy = p1[1] - p0[1]

    if abs(dy) < NEARZEROTOL:
        xi = (p1[0] + p0[0]) / 2.0
    else:
        dx = p1[0] - p0[0]
        r  = dx / dy
        xi = p0[0] + ( (Ni - p0[1]) * r )

    return xi


#--------------------------------------------------------------------
# Calculate the y (N) coordinate corresponding to easting Ei on
#  the line segment (p0,p1)
# Points format is (E, N)
# Assumes there is an intersection,
#  i.e. x0 < Ei < x1 or x1 < Ei < x0
#
def calc_yi(p0, p1, Ei):

    dx = p1[0] - p0[0]

    if abs(dx) < NEARZEROTOL:
        yi = (p1[1] + p0[1]) / 2.0
    else:
        dy = p1[1] - p0[1]
        s = dy / dx
        yi = p0[1] + ( (Ei - p0[0]) * s )

    return yi


#--------------------------------------------------------------------
# Insert intersection into target with increasing E
#
def insert_ordered_E_inc( target, ipt ):

    # X is Easting
    int_x = ipt.pt[0]

    i = 0
    inserted = False
    for item in target:
        pt_x = item.pt[0]
        if int_x < pt_x:
            target.insert(i, ipt)
            inserted = True
            break
        i += 1

    if not inserted:
        target.append(ipt)


#--------------------------------------------------------------------
# Insert intersection into target with decreasing E
#
def insert_ordered_E_dec( target, ipt ):

    # X is Easting
    int_x = ipt.pt[0]

    i = 0
    inserted = False
    for item in target:
        pt_x = item.pt[0]
        if int_x > pt_x:
            target.insert(i, ipt)
            inserted = True
            break
        i += 1

    if not inserted:
        target.append(ipt)
    

#--------------------------------------------------------------------
# Find the intersection point(s) of the line (p0,p1) with the four
# boundaries of the bbox. 
# Each intersection returned consists of the intersection point and 
# a boolean indicating if the intersection is on the actual bounding
# polygon (True), or only on one of four infinite constant-x or constant-y
# lines that form the bounding rectangle but outside the limits of the
# actual bounding box (False).
# There may be up to 4 intersections, up to two may be 'True'. 
# The intersections are ordered on increasing distance from p0.
#
def find_intersections(bb, p0, p1, debug=False):

    ipoints = []

    minE = bb.ll[0]
    minN = bb.ll[1]
    maxE = bb.ur[0]
    maxN = bb.ur[1]

    if debug: print "find_intersections() - bb: " + `bb`

    def isect_with_constN(n):
        # proceed only if there is indeed an intersection
        if      (p0[1] < n and p1[1] > n) or \
                (p0[1] > n and p1[1] < n):
            xi = calc_xi(p0, p1, n)
            is_on_bound = (xi >= minE and xi <= maxE)
            intersection =  Isection( (xi, n), is_on_bound )
            # keep the intersections ordered
            if len(ipoints) == 0 or \
                    ( abs(p0[0] - xi) > abs(p0[0] - ipoints[0].pt[0]) ):
                ipoints.append (intersection )
            else:
                ipoints.insert(0, intersection)

    isect_with_constN(minN)
    isect_with_constN(maxN)

    for x in (minE, maxE):
        # proceed only if there is indeed an intersection
        if      (p0[0] < x and p1[0] > x) or \
                (p0[0] > x and p1[0] < x):
            yi = calc_yi(p0, p1, x)
            is_on_bound = (yi >= minN and yi <= maxN)
            ipt =  Isection((x, yi), is_on_bound)

            if p0[0] < p0[1]:
                insert_ordered_E_inc( ipoints, ipt )
            else:
                insert_ordered_E_dec( ipoints, ipt )

    return ipoints


#--------------------------------------------------------------------
# Find corners
#
def find_corner(bb, ipt):

    def closest(p, bb0, bb1):
        if abs(p-bb0) < abs(p-bb1):
            return bb0
        else:
            return bb1

    pt = ipt.pt

    minx = bb.ll[0]
    maxx = bb.ur[0]
    miny = bb.ll[1]
    maxy = bb.ur[1]

    # X is Easting, Y is Northing
    corner_E = closest(pt[0], minx, maxx)
    corner_N = closest(pt[1], miny, maxy)

    return (corner_E, corner_N)


#--------------------------------------------------------------------
# Is point in polygon
#
def is_pt_in_poly(poly, pt):
    ogr_pt = ogr.Geometry(ogr.wkbPoint)
#    ogr_pt.AddPoint_2D(pt[1], pt[0])  MN XXX
    ogr_pt.AddPoint_2D(pt[0], pt[1])
    return ogr_pt.Within(poly)

#--------------------------------------------------------------------
# Do the two 2D points have the same coordiantes.
#
def same_point(p0, p1):
    return \
        p0[0] == p1[0] and p0[1] == p1[1]


#--------------------------------------------------------------------
# Append pt to clipped list if pt is not the same as eithr of the
#  last two points already in the list.
#
def append_if_not_same(clipped, pt):

    len_clipped = len(clipped)
    if 0 == len_clipped:
        clipped.append(pt)
    elif 1 == len_clipped:
        if not same_point(clipped[0], pt):
            clipped.append(pt)
    else:
        if not same_point(clipped[-1], pt) and \
                not same_point(clipped[-2], pt):
            clipped.append(pt)
                            

#--------------------------------------------------------------------
# Clips a polygon against a bounding box.
# Returns a list of points representing a new polygon,
# which is either inside the bbox (nluding the
#  bbox boundaries. A zero-length polygon is returned if the input
# does not intersect the bbox. If the bbox is completerly inside the
# bbox then the new poly's vertices are the corners of the bbox.
#
#  bb: bounding box
#  poly: GeometryRef
#
def clip_poly(bb, poly, debug=False):

    #MN XXX
    #plot_poly(grdbg.add_line, poly, is_x_first=True)

    clipped = []
    gcount = poly.GetGeometryCount()
    if gcount == 0: return clipped

    # Use the outer ring only; ignore any innner holes.
    ring = poly.GetGeometryRef(0)
    n = ring.GetPointCount()
        
    p0 = ring.GetPoint(0)
    # x is first, but we use norting first
    p0_is_inside = is_pt_in_BB(bb, p0)


    if debug:
        print " cccc n poly points (outer-ring): "+`n`
        print "bb: " + `bb`
        print "p0: "+`p0` + ", inside: "+`p0_is_inside`

    if p0_is_inside:
        clipped.append(p0)

    for i in range(1,n):

        p1 = ring.GetPoint(i)
        p1_is_inside = is_pt_in_BB(bb, p1)

        #prt_debug = False
        #if debug and (i < 12 or 0 == i % 4000):
        #    prt_debug = True
        #if prt_debug:
        #    print "p: "+`p1` + ", p-in: "+`p1_is_inside` + ",  p0-in: "+`p0_is_inside`

        if p0_is_inside and p1_is_inside:
            clipped.append(p1)
            
        else:

            # one of both of p0 or p1 is/are outside
            ipts = find_intersections(bb, p0, p1)

            # MN XXX
            # dd = i<6 and LOCAL_DEBUG
            # if dd and (\
            #     (    p0[0]<bb.ll[0] and p1[0]>bb.ll[0]) or \
            #         (p1[0]<bb.ll[0] and p0[0]>bb.ll[0]) ):
            #     print "p0: " + `p0` + ", p1:" + `p1`,
            #     if len(ipts)==0:
            #         print " NO INT"
            #     else:
            #         print ", Ipts:" ,
            #         for ii in ipts:
            #             print "  "+`ii`,
            #         print

            # ipts are ordered starting with the one closest to p0
            for ipt in ipts:

                if ipt.is_on_bound:
                    clipped.append(ipt.pt)
                
                else:

                    # The  intersection is only with one of the four
                    # infinite constant-x or constant-y lines that form
                    # the bounding rectangle, but the interesection with
                    # these infinite lines is  outside the limits of the
                    # actual bounding box.
                    # This implies that a corner points may potentially be
                    # part of the new clippled polygon.
                    # To qualify as belonging to the new clipped polygon
                    # the candidate corner point must be inside the original
                    # polygon.
                    corner = find_corner(bb, ipt)
                    if LOCAL_DEBUG: print " --> corner: "+`corner`,
                    if is_pt_in_poly(poly, corner):
                        if LOCAL_DEBUG: print "  INSIDE"
                        append_if_not_same(clipped, corner)
                    else:
                        if LOCAL_DEBUG: print " OUT"
                            

        p0 = p1
        p0_is_inside = p1_is_inside

    if len(clipped) > 1:
        # ensure the newly generated ring is closed
        if not same_point(clipped[0], clipped[-1]):
            clipped.append(clipped[0])

    return clipped


#--------------------------------------------------------------------
# Does the aoi have any points in common with poly.
#
def points_coincide(aoi, poly):

    aoi_pts = (
        (aoi.ll[0], aoi.ll[1]),
        (aoi.ll[0], aoi.ur[1]),
        (aoi.ur[0], aoi.ur[1]),
        (aoi.ur[0], aoi.ll[1]) )

    g_count = poly.GetGeometryCount()

    for apt in aoi_pts:

        for j in range(g_count):

            g1 = poly.GetGeometryRef(j)
            n_points = g1.GetPointCount()

            for p in range(n_points):
                ppt = g1.GetPoint(p)

                if same_point(apt, ppt):
                    return True

    return False


#####################################################################
# ----------------- Stand-alone test/debug --------------------------
#####################################################################
#
def plot_bb(plotter, bb, color=None):
    p0x = bb.ll[0];  p0y = bb.ll[1]
    p1x = bb.ur[0];  p1y = bb.ll[1]
    p2x = bb.ur[0];  p2y = bb.ur[1]
    p3x = bb.ll[0];  p3y = bb.ur[1]
    plotter(p0x,p0y, p1x,p1y, color)
    plotter(p1x,p1y, p2x,p2y, color)
    plotter(p2x,p2y, p3x,p3y, color)
    plotter(p3x,p3y, p0x,p0y, color)

def plot_poly(plotter, poly, color=None, is_x_first=True):
    g_count = poly.GetGeometryCount()
    print " "+`poly.GetGeometryName()`+" g_count: "+`g_count`+", pt_counts:",
    for j in range(g_count):
        g1 = poly.GetGeometryRef(j)
        n_points = g1.GetPointCount()
        if n_points < 2:
            print "    **** <2 pts, ",
            break

        if j < 32:
            print `n_points`+", ",

        p0 = g1.GetPoint(0)
        for p in range(1,n_points):
            p1 = g1.GetPoint(p)
            if is_x_first: plotter(p0[0],p0[1], p1[0],p1[1], color)
            else: plotter(p0[1],p0[0], p1[1],p1[0], color)
            p0 = p1
    print


def plot_geom(plotter, geom, color=None):
    count = geom.GetGeometryCount()
    print "plotting "+`count`+" geometries"
    for i in range(count):
        poly = geom.GetGeometryRef(i)
        plot_poly(plotter, poly, color)


def plot_feature_data(plotter, layer, color=None):

    feature = layer.GetNextFeature()
    if not feature:
        logger.error("NO FEATURE in layer!")

    while feature:
        geom = feature.GetGeometryRef()
        if not geom:
            logger.error("NO GEOM!")
            break
        plot_geom(plotter, geom, color)
        feature = layer.GetNextFeature()


def print_ring(ring):
    pt_count = ring.GetPointCount()
    print " ring pt_count: "+`pt_count`
    if pt_count > 55:
        print "    *** printing only first 55 points"
        pt_count = 55
    for p in range(pt_count):
        pt = ring.GetPoint(p)
        print `pt`


def print_geom(geom):
    count = geom.GetGeometryCount()
    for i in range(count):
        ring  = geom.GetGeometryRef(i)
        print_ring(ring)


def print_poly(poly, max_points=50):
    g_count = poly.GetGeometryCount()
    print "  "+`poly.GetGeometryName()`+" g_count: "+`g_count`
    for j in range(g_count):
        g1 = poly.GetGeometryRef(j)
        n_points = g1.GetPointCount()
        if n_points < 2:
            print "    **** less than 2 points"
            break

        if j < 54:
            print "      n_points: " + `n_points`

        k = 0
        if n_points > max_points:
            print " Too many points ("+`n_points`+"), showing first "+`max_points`
            n_points = max_points
        for p in range(n_points):
            pt = g1.GetPoint(p)
            print `pt`+", ",
            k += 1
            if 0 == k%2: print
        print


def print_feature_data(layer):
    feature = layer.GetNextFeature()
    if not feature:
        logger.error("NO FEATURE in layer!")

    while feature:
        geom = feature.GetGeometryRef()
        if not geom:
            logger.error("NO GEOM!")
            break
        count = geom.GetGeometryCount()
        print " feature "+`geom.GetGeometryName()`+", geom count="+`count`
        for i in range(count):
            poly = geom.GetGeometryRef(i)

            g_count = poly.GetGeometryCount()
            print "  "+`poly.GetGeometryName()`+" g_count: "+`g_count`
            for j in range(g_count):
                g1 = poly.GetGeometryRef(j)
                n_points = g1.GetPointCount()
                if j < 6 or not j%500:
                    print "      n_points: " + `n_points`
                    print "      envelope: " + `g1.GetEnvelope()`
                    for p in range(n_points):
                        if n_points<50 :
                            print "(" + `g1.GetPoint(p)` + "), "
                    print
                #chull = poly.ConvexHull()
                #nn = chull.ExportToWkt()
                #print " nn: " + `nn`
                #chull = None

        feature = layer.GetNextFeature()


def check_feature_data(layer):
    layer.ResetReading()
    feature = layer.GetNextFeature()
    if not feature:
        logger.error("NO FEATURE in layer!")
    while feature:
        geom = feature.GetGeometryRef()
        if not geom:
            logger.error("NO GEOM!")
            break
        count = geom.GetGeometryCount()
        for i in range(count):
            poly = geom.GetGeometryRef(i)
            p_count = poly.GetGeometryCount()
        feature = layer.GetNextFeature()

    
def mem_test(shpfile, aoi_bb):
    # test freeing of memory
    print "test freeing of memory"

    import time, resource, sys
    i = 0
    usage=resource.getrusage(resource.RUSAGE_SELF)
    print 'rss=' + `usage.ru_maxrss`
    while i<600:
        cc2 = coastline_cache_from_aoi(shpfile, None, aoi_bb)
        cclayer = cc2.GetLayer()
        #print "Extent: " + `cclayer.GetExtent()`
        #print_feature_data(cclayer)
        check_feature_data(cclayer)
        destrory_coastline_cache(cc2)
        print ".",
        sys.stdout.flush()
        if not i%50:
            usage=resource.getrusage(resource.RUSAGE_SELF)
            print
            print 'rss=' + `usage.ru_maxrss`
        i += 1
    print "done"


if __name__ == '__main__':

    import xml.etree.ElementTree as ET
    from ie_xml_parser import \
        set_logger, \
        WCS_TYPE_DRAFT201
    set_logger(logger)

    test_cd_xml_template = """<?xml version="1.0" encoding="ISO-8859-1"?>
    <drtest>
    <gmlcov:metadata
         xmlns:gmlcov="http://www.opengis.net/gmlcov/1.0"
         xmlns:wcseo="http://www.opengis.net/wcseo/1.0" 
         xmlns:gml="http://www.opengis.net/gml/3.2"
         xmlns:om="http://www.opengis.net/om/2.0"
         xmlns:eop="http://www.opengis.net/eop/2.0">
    <gmlcov:Extension>
    <wcseo:EOMetadata>
    <eop:EarthObservation>
    <om:featureOfInterest >
    <eop:Footprint gml:id="uuid_78ca170c-6995-4fe8-86e4-4eb104b802df">
      <eop:multiExtentOf>
        <gml:MultiSurface 
             srsName="urn:ogc:def:crs:EPSG:6.3:4326"
             gml:id="dream-test-m1" >
          <gml:surfaceMember>
            <gml:Polygon gml:id="dream-test-p1">
              <gml:exterior> <gml:LinearRing>
                  <gml:posList>%s</gml:posList>
              </gml:LinearRing> </gml:exterior>
            </gml:Polygon>
          </gml:surfaceMember>
        </gml:MultiSurface>
      </eop:multiExtentOf>
    </eop:Footprint>
    </om:featureOfInterest>
    </eop:EarthObservation>
    </wcseo:EOMetadata> </gmlcov:Extension> </gmlcov:metadata>
    </drtest>
    """
    tmp = """
    <eop:multiExtentOf xmlns:eop="http://www.opengis.net/eop/2.0">
    </eop:multiExtentOf>
    """

    wcs_type = WCS_TYPE_DRAFT201
    data_dir = os.path.join( os.getcwd(), 'media', 'etc', 'coastline_data' )
    shpfile  = os.path.join( data_dir, 'ne_10m_land.shp' )

    def test_isect():

        bb1_ll =  (48.0, 1.0)
        bb1_ur =  (49.0, 2.0)
        aoi_bb = Bbox(bb1_ll, bb1_ur)

        print "test_isect, bb: " + `aoi_bb`

        p0 = (45, 1.7)
        p1 = (48.2, 3.5)

        ii = find_intersections(aoi_bb, p0, p1, True)
        print "ii: " + `ii`
        ii = find_intersections(aoi_bb, p1, p0, True)
        print "ii-2: " + `ii`


    def test_live(aoi_bb):

        print "test_live, bb: " + `aoi_bb`

        ccoastline = coastline_cache_from_aoi(shpfile, None, aoi_bb)
        cclayer = ccoastline.GetLayer()

        # extent is returned as ( MinN, MaxN, MinE, MaxE)
        if have_tk:
            extent = cclayer.GetExtent()
            print 'test_live - cclayer extent: '+`extent`
            plot_feature_data(grdbg.add_line, cclayer)
       
        print

    def test_dk(aoi_bb):

        n_errors = 0

        ccoastline = coastline_cache_from_aoi(shpfile, None, aoi_bb)
        cclayer = ccoastline.GetLayer()

        # extent is returned as ( MinN, MaxN, MinE, MaxE)
        if have_tk:
            extent = cclayer.GetExtent()
            print 'cclayer extent: '+`extent`
            plot_feature_data(grdbg.add_line, cclayer)
        else:
            print "Cache Extent: " + `cclayer.GetExtent()`
            print "Cache content:"
            print_feature_data(cclayer)

        # polygon outside of the cache region:
        print " ------ polygon outside coastline cache -----"
        #    "56.7572 3.4195 56.9073 4.4739 56.4406 4.2201 56.7572 3.4195 56.7572 3.4195"
        out_poly_coords = \
            "53.92 8.06 " + \
            "53.92 8.3 " + \
            "54.1  8.3 " + \
            "54.1  8.06 " + \
            "53.92 8.06 "
        out_poly_xml = test_cd_xml_template % out_poly_coords
        cd = ET.fromstring(out_poly_xml)
        if have_tk:
            out_geom = extract_geom(cd, 'outside', wcs_type)
            print "out_geom:  " + `out_geom.GetEnvelope()`
            out_env = out_geom.GetEnvelope()
            plot_poly(grdbg.add_line, out_geom, "red")

        if not coastline_ck(cd, 'outside', ccoastline, wcs_type):
            print "outside chck OK"
        else:
            print "outside chck FAILED"
            n_errors += 1
        print

        # polygon inside of the cache region:
        print " ------ polygon inside coastline cache -----"
        in_poly_coords = \
            "52.6 8.4 "+\
            "52.6 8.7 "+\
            "53.0 8.7 "+\
            "53.0 8.4 "+\
            "52.6 8.4"
        in_poly_xml = test_cd_xml_template % in_poly_coords
        cd = ET.fromstring(in_poly_xml)
        if have_tk:
            in_geom = extract_geom(cd, 'inside', wcs_type)
            plot_poly(grdbg.add_line, in_geom, "blue")

        if coastline_ck(cd, 'inside', ccoastline, wcs_type):
            print "inside chck OK"
        else:
            print "inside chck FAILED"
            n_errors += 1
        print

        if n_errors:
            print "Errors: " + `n_errors`
        else:
            print "   ---- DK Tests OK ---- \n"


    def std_tests():
        grdbg.set_xform(
            minX=  0.8, maxX=9.5,
            minY= 47.5, maxY=56.5)

        #test_isect()

        # around Denmark
        #dk_ll =  (50.282,  5.60656)
        #dk_ur =  (59.71651, 13.7335)
        # test2 
        #dk_ll =  (49.853678, 14.123)
        #dk_ur =  (50.71651,  15.369 )

        dk_ll =  (8.0, 50.0)
        dk_ur =  (12.3, 55.0)

        bb = Bbox(dk_ll, dk_ur)

        plot_bb(grdbg.add_line, bb, "green")
        test_dk(bb)

        bb1_ll =  (2.5, 48.9495)
        bb1_ur =  (3.1, 51.2)
        bb = Bbox(bb1_ll, bb1_ur)
        plot_bb(grdbg.add_line, bb, "blue")

        test_live(bb)

        #(1.55, 48.8504),(1.6, 48.95)

        bb1_ll =  (1.55, 48.8504)
        bb1_ur =  (1.603, 48.9495)
        bb = Bbox(bb1_ll, bb1_ur)
        plot_bb(grdbg.add_line, bb, "blue")

        test_live(bb)

    def special_tests():

        grdbg.set_xform(
            minX=  -3.5, maxX=2.5,
            minY= 42.0, maxY=48.0)

        bb1_ll =  (-2.16, 44.379)
        bb1_ur =  (-1.67, 44.795)
        bb = Bbox(bb1_ll, bb1_ur)
        plot_bb(grdbg.add_line, bb, "blue")

        ccoastline = coastline_cache_from_aoi(shpfile, None, bb)
        cclayer = ccoastline.GetLayer()

        # extent is returned as ( MinN, MaxN, MinE, MaxE)
        if have_tk:
            extent = cclayer.GetExtent()
            print 'cclayer extent: '+`extent`
            plot_feature_data(grdbg.add_line, cclayer)
        else:
            print "Cache Extent: " + `cclayer.GetExtent()`
            print "Cache content:"
            print_feature_data(cclayer)


        # polygon inside of the cache region:
        print " ------ polygon inside coastline cache -----"
        in_poly_coords = \
            "44.5 -2.0 "+\
            "44.5 -1.8 "+\
            "44.7 -1.8 "+\
            "44.7 -2.0 "+\
            "44.5 -2.0"
        in_poly_xml = test_cd_xml_template % in_poly_coords
        cd = ET.fromstring(in_poly_xml)
        if have_tk:
            in_geom = extract_geom(cd, 'inside', wcs_type)
            plot_poly(grdbg.add_line, in_geom, "blue")

        if coastline_ck(cd, 'inside', ccoastline, wcs_type):
            print " Special Test: FAILED - expected coastline_ck to return false."
        else:
            print " Special Test: OK"
        print


#------------ main --------------
#
    if have_tk:

        special = False

        if  special:
            special_tests()
        else:
            std_tests()
            

        print "Starting tk main loop"
        tk_root.mainloop()


    print "Done"
