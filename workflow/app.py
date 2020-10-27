# Import python modules
import numpy as np
import geopandas as gpd
import netCDF4
import sys, os
sys.path.append("../scripts")

import spatial_functions
import aem_utils
import netcdf_utils
import modelling_utils
import plotting_functions as plots
import warnings
import pandas as pd
warnings.filterwarnings('ignore')
# Dash dependencies
import plotly.express as px
from jupyter_dash import JupyterDash
import dash
from dash.dependencies import Input, Output
import dash_core_components as dcc
import dash_html_components as html
import dash_table
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# The actual inversion data are stored on disk as netcdf files. NetCDF is an efficient format for storing
# self-describing containerised data.
# The implementation of netcdf for AEM line data was done by Alex Ip using his geophys_utils package.
# https://github.com/GeoscienceAustralia/geophys_utils/tree/master/geophys_utils


root = r"C:\Users\symin\OneDrive\Documents\GA\AEM\LCI"

# Define path to the netcdf file
infile = os.path.join(root, "Injune_lci_MGA55.nc")

# Create an instance
lci = aem_utils.AEM_inversion(name = 'Laterally Contrained Inversion (LCI)',
                              inversion_type = 'deterministic',
                              netcdf_dataset = netCDF4.Dataset(infile))

# Directory in which the grids are located
infile = os.path.join(root, "grids\\Injune_layer_grids.p")

# Run function
lci.load_lci_layer_grids_from_pickle(infile)

# Path to netcdf file
infile = r"C:\Users\symin\OneDrive\Documents\GA\AEM\rjmcmc\Injune_petrel_rjmcmc_pmaps.nc"


# Create instance
rj = aem_utils.AEM_inversion(name = 'GARJMCMCTDEM',
                             inversion_type = 'stochastic',
                             netcdf_dataset = netCDF4.Dataset(infile))

##TODO add nsamples as a scalar variable
rj.nsamples = np.sum(rj.data['log10conductivity_histogram'][0], axis = 1)[0]


# Now we have the lines we can grid the lci conductivity data onto vertical grids (known as sections)
# this is the easiest way to visualise the AEM conuctivity in 2-dimensions

# Assign the lci variables to grid
grid_vars = ['conductivity', 'data_residual', 'depth_of_investigation']


# Define the resolution of the sections
xres, yres = 40., 5.

# We will use the lines from the rj

lines = [200101, 200401, 200501, 200801,
         200901, 201001, 201101, 201201, 201301, 201401, 201501,
         201601, 201701, 201801, 201901, 202001, 202101, 202201,
         202301, 202401, 202501, 202601, 202701, 202801, 912011]

# Define the output directory if saving the grids as hdf plots

hdf5_dir = r"C:\temp\Injune_hdf5"

# if the directory doesn't exist, then create it
if not os.path.exists(hdf5_dir):
    os.mkdir(hdf5_dir)

# Gridding takes a few minutes so I pre-gridded them for you. The lci.grid_sections()
# function below will do the gridding for you. Instead we will use the load_sectoin_from_file()
# function, which loads hdf5 files produced using the grid_sections() function


#lci.grid_sections(variables = grid_vars, lines = lines, xres = xres, yres = yres,
#                  return_interpolated = True, save_hdf5 = True, hdf5_dir = hdf5_dir)

lci.load_sections_from_file(hdf5_dir, grid_vars, lines = lines)

# Grid the rj sections

# Assign the lci variables to grid
grid_vars = ['conductivity_p10', 'conductivity_p50', 'conductivity_p90', 'interface_depth_histogram',
             'misfit_lowest', 'misfit_average']

# Define the resolution of the sections
xres, yres = 50., 2.

# We will use the lines from the rj

lines = [200101, 200401, 200501, 200801,
         200901, 201001, 201101, 201201, 201301, 201401, 201501,
         201601, 201701, 201801, 201901, 202001, 202101, 202201,
         202301, 202401, 202501, 202601, 202701, 202801, 912011]

# Define the output directory if saving the grids as hdf plots

hdf5_dir = r"C:\Temp\SSC_hdf5_rj"

# if the directory doesn't exist, then create it
if not os.path.exists(hdf5_dir):
    os.mkdir(hdf5_dir)

#rj.grid_sections(variables = grid_vars, lines = lines, xres = xres, yres = yres,
#                  return_interpolated = True, save_hdf5 = True, hdf5_dir = hdf5_dir)

rj.load_sections_from_file(hdf5_dir, grid_vars, lines = lines)

# Create polylines
lci.create_flightline_polylines()

gdf_lines = gpd.GeoDataFrame(data = {'lineNumber': lci.flight_lines.keys(),
                                     'geometry': lci.flight_lines.values()},#[x.wkt for x in lci.flight_lines.values()]},
                             geometry= 'geometry',
                             crs = 'EPSG:28353')

gdf_lines = gdf_lines[np.isin(gdf_lines['lineNumber'], lines)]

# Using this gridding we find the distance along the line for each site
# Iterate through the lines
rj.distance_along_line = {}

for lin in lines:
    # Get a line mask
    line_mask = netcdf_utils.get_lookup_mask(lin, rj.data)
    # get the coordinates
    line_coords = rj.coords[line_mask]

    dists = spatial_functions.xy_2_var(lci.section_data[lin],
                                      line_coords,
                                      'grid_distances')
    # Add a dictionary with the point index distance along the line to our inversion instance
    rj.distance_along_line[lin] = pd.DataFrame(data = {"point_index": np.where(line_mask)[0],
                                                       "distance_along_line": dists,
                                                       'fiducial': rj.data['fiducial'][line_mask]}
                                               ).set_index('point_index')


# Setup the model
# Create an modelled boundary instance

headings = ["fiducial", "inversion_name",'X', 'Y', 'ELEVATION', "DEM", "DEPTH", "UNCERTAINTY", "Type",
            "BoundaryNm", "BoundConf", "BasisOfInt", "OvrConf", "OvrStrtUnt", "OvrStrtCod", "UndStrtUnt",
           "UndStrtCod", "WithinType", "WithinStrt", "WithinStNo", "WithinConf", "InterpRef",
            "Comment", "SURVEY_LINE", "Operator"]

interp_file = r"C:\temp\top_Precipice_interpreted_points.csv"

EP_surface = modelling_utils.modelled_boundary(name = 'Top=Precipice interface',
                                               outfile_path = interp_file,
                                               interpreted_point_headings = headings)
#MP_surface.interpreted_points = pd.read_csv(interp_file)
# Define your surface
surface = EP_surface

# Assign attributes base on what you want to be
# entered into the eggs database
surface.Type = "INTRA_Paleozoic"
surface.OvrStrtUnt = "Evergreen Formation"
surface.OvrStrtCod = 6416
surface.UndStrtUnt = "Precipice Sandstone"
surface.UndStrtCod = 15540
surface.Inversion_name = ""
surface.BoundConf = "M"
surface.BasisOfInt = "IAEM"
surface.OvrConf = "M"
surface.InterpRef = ""
surface.Comment = ""
surface.Operator = "John Fish"
surface.WithinType = ""
surface.WithinStrt = ""
surface.WithinStNo = ""
surface.WithinConf = ""

line_options = []

for l in lines:
     line_options.append({'label': str(l), 'value': l})

def subset_df_by_line(df_, line, line_col = 'SURVEY_LINE'):
    mask = df_[line_col] == line
    return df_[mask]

# section functions
def xy2fid(x,y, dataset):
    dist, ind = spatial_functions.nearest_neighbours([x, y],
                                                     dataset.coords,
                                                     max_distance = 100.)
    return dataset.data['fiducial'][ind][0]

def interp2scatter(line, gridded_data, interpreted_points, easting_col = 'X',
                   northing_col = 'Y', elevation_col = 'ELEVATION',
                   line_col = 'SURVEY_LINE'):

    utm_coords = np.column_stack((gridded_data[line]['easting'],
                                  gridded_data[line]['northing']))

    df_ = subset_df_by_line(interpreted_points, line, line_col = line_col)

    dist, inds = spatial_functions.nearest_neighbours(df_[[easting_col,northing_col]].values,
                                                      utm_coords, max_distance=100.)

    grid_dists = gridded_data[line]['grid_distances'][inds]
    elevs = df_[elevation_col].values
    fids = df_['fiducial'].values

    return  grid_dists, elevs, fids

def dash_section(line, df_interp, colours, section_kwargs):
    # Create subplots
    fig = make_subplots(rows=2, cols = 1, shared_xaxes=True,
                        vertical_spacing=0.05,
                        row_heights=[0.2, 0.8])

    # plot the data residual
    if section_kwargs['section_plot'] == "lci":
        section_data = lci.section_data
        fig.add_trace(go.Scatter(x = section_data[line]['grid_distances'],
                                 y = section_data[line]['data_residual'],
                                 line=dict(color='black', width=3),
                                 showlegend = False, hoverinfo = None),
                       row = 1, col = 1,)
    else:
        section_data = rj.section_data
        fig.add_trace(go.Scatter(x = section_data[line]['grid_distances'],
                                 y = np.log10(section_data[line]['misfit_lowest']),
                                 line=dict(color='black', width=3),
                                 showlegend = False, hoverinfo = None),
                       row = 1, col = 1,)

    # Create the grid
    if section_kwargs['section_plot'] == "lci":
        fig.add_trace(go.Heatmap(z = np.log10(section_data[line]['conductivity']),
                        zmin = np.log10(section_kwargs['vmin']),
                        zmax = np.log10(section_kwargs['vmax']),
                        x = section_data[line]['grid_distances'],
                        y = section_data[line]['grid_elevations'],
                        colorscale =section_kwargs['cmap'],
                        #hoverlabel=dict(x="Distance along line", y="elevation (mAHD)"),
                        ),
                      row = 2, col = 1,
        )
    elif section_kwargs['section_plot'] == "rj-p50":
        fig.add_trace(go.Heatmap(z = np.log10(section_data[line]['conductivity_p50']),
                        zmin = np.log10(section_kwargs['vmin']),
                        zmax = np.log10(section_kwargs['vmax']),
                        x = section_data[line]['grid_distances'],
                        y = section_data[line]['grid_elevations'],
                        colorscale =section_kwargs['cmap'],
                        #hoverlabel=dict(x="Distance along line", y="elevtion (mAHD)"),
                        ),
                      row = 2, col = 1,
        )

    elif section_kwargs['section_plot'] == 'rj-conf':

        confidence = plots.percentiles2pnci(section_data[line]['conductivity_p10'],
                                            section_data[line]['conductivity_p90'],
                                            upper_threshold = 0.99,
                                            lower_threshold = 0.01)

        fig.add_trace(go.Heatmap(z = confidence,
                        zmin = 0.1,
                        zmax = 0.9,
                        x = section_data[line]['grid_distances'],
                        y = section_data[line]['grid_elevations'],
                        colorscale ="YlGn"
                        #hoverlabel=dict(x="Distance along line", y="elevation (mAHD)"),
                        ),
                      row = 2, col = 1,
        )

    elif section_kwargs['section_plot'] == "rj-lpp":

        fig.add_trace(go.Heatmap(z = section_data[line]['interface_depth_histogram']/rj.nsamples,
                        zmin = 0.01,
                        zmax = 0.7,
                        x = section_data[line]['grid_distances'],
                        y = section_data[line]['grid_elevations'],
                        colorscale ="greys",
                        #hoverlabel=dict(x="Distance along line", y="elevation (mAHD)"),
                        ),
                      row = 2, col = 1,
        )

    # Add the elevation
    fig.add_trace(go.Scatter(x = section_data[line]['grid_distances'],
                             y = section_data[line]['elevation'],
                             line=dict(color='black', width=3),
                             showlegend = False, hoverinfo = None),
                  row = 2, col = 1,)

    # Now we add the rjmcmc sites to the section

    df_rj_sites = rj.distance_along_line[line]

    labels = ["fiducial = " + str(x) for x in df_rj_sites['fiducial']]

    fig.add_trace(go.Scatter(x = df_rj_sites['distance_along_line'].values,
                    y = 20. +np.max(section_data[line]['elevation'])*np.ones(shape = len(df_rj_sites),
                                                                        dtype = np.float),
                    mode = 'markers',
                    hovertext = labels),
                  row = 2, col = 1)

    if len(df_interp) > 1:
        if np.logical_or(section_kwargs['section_plot'] == "rj-p50",
                         section_kwargs['section_plot'] == "lci"):
            # Get the ticks
            tickvals = np.linspace(np.log10(section_kwargs['vmin']),
                                    np.log10(section_kwargs['vmax']),
                                    5)

            ticktext = [str(np.round(x,3)) for x in 10**tickvals]

            fig.update_layout(coloraxis_colorbar=dict(
            title="conductivity",
            tickvals=tickvals,
            ticktext=ticktext,
            ))

        interpx, interpz, fids = interp2scatter(line, section_data, df_interp)

        if len(interpx) > 0:
            labels = ["fiducial = " + str(x) for x in fids]

            fig.add_trace(go.Scatter(x = interpx,
                            y = interpz,
                            mode = 'markers',
                            hovertext = labels,
                            marker = {"color": colours}),
                          row = 2, col = 1
                          )

    # Reverse y-axis
    fig.update_yaxes(autorange=True)

    return fig

def dash_pmap_plot(point_index):
    # Extract the data from the netcdf data
    D = netcdf_utils.extract_rj_sounding(rj, lci,
                                         point_index)
    pmap = D['conductivity_pdf']
    x1,x2,y1,y2 = D['conductivity_extent']
    n_depth_cells, n_cond_cells  = pmap.shape

    x = np.linspace(x1,x2, n_cond_cells)
    y = np.linspace(y2,y1, n_depth_cells)

    fig = px.imshow(img = pmap,
                    x = x, y = y,
                    zmin = 0,
                    zmax = np.max(pmap),
                    aspect = 'auto',
                    color_continuous_scale = 'plasma')
    #  PLot the median, and percentile plots
    fig.add_trace(go.Scatter(x = np.log10(D['cond_p10']),
                             y = D['depth_cells'],
                             mode = 'lines',
                             line = {"color": 'black',
                                     "width": 2.},
                             name = "p10 conductivity"))
    fig.add_trace(go.Scatter(x = np.log10(D['cond_p90']),
                             y = D['depth_cells'],
                             mode = 'lines',
                             line = {"color": 'black',
                                     "width": 2.},
                             name = "p90 conductivity"))
    fig.add_trace(go.Scatter(x = np.log10(D['cond_p50']),
                             y = D['depth_cells'],
                             mode = 'lines',
                             line = {"color": 'gray',
                                     "width": 2.,
                                     'dash': 'dash'},
                             name = "p50 conductivity"))

    return fig


def flightline_map(line):

    fig = go.Figure()

    layer = 1 #TODO create event function
    cond_grid = np.log10(lci.layer_grids['Layer_{}'.format(layer)]['conductivity'])


    x1, x2, y1, y2 = lci.layer_grids['bounds']
    n_y_cells, n_x_cells = cond_grid.shape
    x = np.linspace(x1, x2, n_x_cells)
    y = np.linspace(y2, y1, n_y_cells)

    fig.add_trace(go.Heatmap(z=cond_grid,
                               zmin=-2,#np.log10(section_kwargs['vmin']),
                               zmax=0,#np.log10(section_kwargs['vmax']),
                               x=x,
                               y=y,
                               colorscale="jet",
                               # hoverlabel=dict(x="Distance along line", y="elevation (mAHD)"),
               ))

    for linestring, lineNo in zip(gdf_lines.geometry, gdf_lines.lineNumber):

        if int(lineNo) == int(line):
            c = 'red'
        else:
            c = 'black'
        x, y = linestring.xy

        fig.add_trace(go.Scatter(x = list(x),
                                 y = list(y),
                                 mode = 'lines',
                                 #hovertext = ['Line number = ' + str(lineNo)],
                                 line = {"color": c,
                                         "width": 2.},
                                 name = str(lineNo)))

    # TODO think of replacing this
    xmin, xmax = np.min(rj.data['easting'][:]) - 500., np.max(rj.data['easting'][:]) + 500.
    ymin, ymax = np.min(rj.data['northing'][:]) - 500., np.max(rj.data['northing'][:]) + 500.

    fig.update_layout(yaxis=dict(range=[ymin, ymax]),
                      xaxis=dict(range=[xmin, xmax]))
    return fig



section_kwargs = {'colourbar_label': 'Conductivity (S/m)',
                  'vmin': 0.01,
                  'vmax': 1.,
                  'cmap': 'jet'}

stylesheet = "https://codepen.io/chriddyp/pen/bWLwgP.css"
app = dash.Dash(__name__, external_stylesheets=[stylesheet])

app.layout = html.Div([
    html.Div(
                [
                    html.Div(html.H1("AEM interpretation dash board"),
                             className= "four columns"),
                    html.Div([html.H4("Select section"),
                             dcc.Dropdown(id = "section_dropdown",
                                            options=[
                                                    {'label': 'laterally constrained inversion',
                                                     'value': 'lci'},
                                                    {'label': 'garjmcmctdem - p50',
                                                     'value': 'rj-p50'},
                                                   {'label': 'garjmcmcm - certainty',
                                                     'value': 'rj-conf'},
                                                    {'label': 'garjmcmctdem - layer probability',
                                                     'value': 'rj-lpp'}],
                                            value="lci"),

                             ],className = "four columns"),
                    html.Div([html.H4("Select line"),
                             dcc.Dropdown(id = "line_dropdown",
                                            options=line_options,
                                            value= int(line_options[0]['label'])),
                             ],className = "four columns")
                ], className = 'row'
            ),
    html.Div(
            [
                html.Div(html.Pre(id='click-data'),
                         className = "four columns"),
                html.Div(className = "four columns"),
                html.Div(html.Button('Update section', id='update', n_clicks=1),
                         className= "four columns"),
             ], className = "row"),
    html.Div(
        html.Div(
            dcc.Graph(
                id='section_plot',
                figure = {}),
        )
    ),
    html.Div([html.Div(
        dash_table.DataTable(id='interp_table',
                                    css=[{'selector': '.row', 'rule': 'margin: 0'}],
                                    fixed_columns={ 'headers': True},#, 'data': 1 },
                                    sort_action="native",
                                    sort_mode="multi",
                                    row_selectable="multi",
                                    row_deletable=True,
                                    selected_columns=[],
                                    selected_rows=[],
                                    style_header={'backgroundColor': 'rgb(30, 30, 30)',
                                               'height': '40px'},
                                    style_cell={
                                                 'backgroundColor': 'rgb(50, 50, 50)',
                                                 'color': 'white',
                                                 'minHeight': '50px',
                                                 'minWidth': '0px', 'maxWidth': '800px',
                                                 'whiteSpace': 'normal',
                                                 'font-size': '12px'
                                             },
                                  style_table={
                                              'maxHeight': '1000px',
                                              'overflowY': 'scroll',
                                              'maxWidth':  '1000px',
                                              'overflowX': 'scroll'})
                                        , className = "four columns"),
        html.Div(html.Div(id='poly_line_plot'), className = "four columns"),
        html.Div(html.Div(id='pmap'), className = "four columns"),]

             ),

])

@app.callback(
    [Output('interp_table', 'data'),
    Output('interp_table', 'columns')],
    [Input("line_dropdown", 'value'),
     Input("update", 'n_clicks')])
def update_data_table(value, nclicks):
    if nclicks >0:
        df_ss = subset_df_by_line(surface.interpreted_points,
                                  line = value)
        return df_ss.to_dict('records'), [{"name": i, "id": i} for i in df_ss.columns]

@app.callback(
    Output('section_plot', "figure"),
    [Input("line_dropdown", 'value'),
     Input("section_dropdown", 'value'),
     Input('interp_table', "derived_virtual_data"),
     Input('interp_table', "derived_virtual_selected_rows")])
def update_section(line, section_plot, rows, derived_virtual_selected_rows):
    # When the table is first rendered, `derived_virtual_data` and
    # `derived_virtual_selected_rows` will be `None`. This is due to an
    # idiosyncrasy in Dash (unsupplied properties are always None and Dash
    # calls the dependent callbacks when the component is first rendered).
    # So, if `rows` is `None`, then the component was just rendered
    # and its value will be the same as the component's dataframe.
    # Instead of setting `None` in here, you could also set
    # `derived_virtual_data=df.to_rows('dict')` when you initialize
    # the component.
    if derived_virtual_selected_rows is None:
        derived_virtual_selected_rows = []

    dff = surface.interpreted_points if rows is None else pd.DataFrame(rows)

    colours = ['pink' if i in derived_virtual_selected_rows else 'white'
              for i in range(len(dff))]

    section_kwargs['section_plot'] = section_plot

    fig = dash_section(line, dff, colours, section_kwargs)

    return fig

@app.callback(
    [Output('poly_line_plot', 'children')],
    [Input("line_dropdown", 'value')])
def update_polyline_plot(value):
    fig = flightline_map(value)
    return [
        dcc.Graph(
            id='polylines',
            figure=fig
            ),
    ]

@app.callback(
    Output('click-data', 'children'),
    [Input('section_plot', 'clickData'),
     Input("line_dropdown", 'value')])
def update_interp_table(clickData, line):
    if clickData is not None:
        if clickData['points'][0]['curveNumber'] == 1:
            eventxdata, eventydata = clickData['points'][0]['x'], clickData['points'][0]['y']
            min_idx = np.argmin(np.abs(lci.section_data[line]['grid_distances'] - eventxdata))

            easting = lci.section_data[line]['easting'][min_idx]
            northing = lci.section_data[line]['northing'][min_idx]
            elevation = lci.section_data[line]['elevation'][min_idx]
            depth =  elevation - eventydata
            fid = xy2fid(easting,northing, lci)

            # append to the surface object interpreted points
            interp = {'fiducial': fid,
                      'inversion_name': "lci",
                      'X': np.round(easting,0),
                      'Y': np.round(northing,0),
                      'DEPTH': np.round(depth,0),
                      'ELEVATION': eventydata,
                      'DEM': elevation,
                      'UNCERTAINTY': np.nan, # TODO implement
                      'Type': surface.Type,
                     'BoundaryNm': surface.name,
                     'BoundConf': surface.BoundConf,
                     'BasisOfInt': surface.BasisOfInt,
                     'OvrConf': surface.OvrConf,
                     'OvrStrtUnt': surface.OvrStrtUnt,
                     'OvrStrtCod': surface.OvrStrtCod,
                     'UndStrtUnt': surface.UndStrtUnt,
                     'UndStrtCod': surface.UndStrtCod,
                     'WithinType': surface.WithinType,
                     'WithinStrt': surface.WithinStrt,
                     'WithinStNo': surface.WithinStNo,
                     'WithinConf': surface.WithinConf,
                     'InterpRef': surface.InterpRef,
                     'Comment': surface.Comment,
                     'SURVEY_LINE': line,
                     'Operator': surface.Operator,
                      "point_index": min_idx
                       }
            df = pd.DataFrame(interp, index = [0])

            surface.interpreted_points = surface.interpreted_points.append(df)#, verify_integrity = True)

            return "Last interpretation was ", eventxdata, " along line and ", eventydata, " mAHD"

@app.callback(
    Output('pmap', 'children'),
    Input('section_plot', 'clickData'))
def update_pmap_plot(clickData):
    if clickData is not None:
        if clickData['points'][0]['curveNumber'] == 3:
            point_idx = clickData['points'][0]['pointIndex']
            fig = dash_pmap_plot(point_idx)
            return [
                    dcc.Graph(
                        id='pmap_plot',
                        figure=fig
                        ),
                    ]

app.run_server(debug = True)#mode='external', port=8060)