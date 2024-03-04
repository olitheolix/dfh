import { useState, useEffect } from 'react';
import Box from '@mui/material/Box';
import Switch from '@mui/material/Switch';
import { DataGrid, GridRowsProp, GridColDef } from '@mui/x-data-grid';
import { GridToolbar } from '@mui/x-data-grid';
import { PodList } from './BackendInterfaces'

const label = { inputProps: { 'aria-label': 'Switch demo' } };

export default function K8sPodList({ appId, envId }: { appId: string, envId: string }) {
    const columnDefs: GridColDef[] = [
        { field: 'namespace', headerName: 'Namespace', width: 150 },
        { field: 'name', headerName: 'Name', width: 350 },
        { field: 'ready', headerName: 'Ready', width: 100 },
        { field: 'phase', headerName: 'Status', width: 100 },
        { field: 'message', headerName: 'Message', width: 100 },
        { field: 'reason', headerName: 'Reason', width: 100 },
        { field: 'restarts', headerName: 'Restarts', width: 100 },
        { field: 'age', headerName: 'Age', width: 150 },
        { field: 'col3', headerName: 'Column 3', width: 150, renderCell: (params) => params.value },
    ];

    const [rows, setRows] = useState<GridRowsProp>([]);

    // Populate the Pod list when mounting the component and periodically refresh it.
    useEffect(() => {
        const fetchData = () => {
            fetch(`/api/crt/v1/pods/${appId}/${envId}`)
                .then(response => response.json())
                .then(jsonData => {
                    const podList: PodList = jsonData as PodList;

                    // Augment each row with a third column that houses a Switch.
                    const rowsWithId = podList.items.map((row, _) => ({ ...row, col3: <Switch {...label} defaultChecked /> }));
                    setRows(rowsWithId);
                })
                .catch(error => {
                    console.error('Error fetching data:', error);
                });
        };

        fetchData();
        const intervalId = setInterval(fetchData, 2000);
        return () => clearInterval(intervalId);
    }, []);

    return (
        <Box sx={{ height: 400, width: 1 }}>
            <DataGrid
                disableColumnFilter
                disableColumnSelector
                disableDensitySelector
                rows={rows}
                columns={columnDefs}
                slots={{ toolbar: GridToolbar }}
                slotProps={{
                    toolbar: {
                        showQuickFilter: true,
                    },
                }}
            />
        </Box>
    );
}
