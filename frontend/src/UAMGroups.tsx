import React from 'react';
import { useState, useEffect } from 'react';
import { DataGrid, GridToolbar, GridEventListener, GridColDef, GridSortModel, GridRowSelectionModel } from '@mui/x-data-grid';
import { CircularProgress, Button, Paper, Typography, Box, Dialog, DialogTitle, DialogContent, DialogActions, Autocomplete, TextField } from '@mui/material';
import { UAMUser, UAMGroup } from './UAMInterfaces'
import Grid from '@mui/material/Grid2';

import Title from './Title';


function ShowAddGroup({ isOpen, setIsOpen }: { isOpen: boolean, setIsOpen: React.Dispatch<React.SetStateAction<boolean>> }) {
    const [options, setOptions] = useState<string[]>([]);
    const [selectedUser, setSelectedUser] = useState<string | null>(null);

    useEffect(() => {
        // Fetch the list of users from the /users endpoint when the dialog opens
        if (isOpen) {
            fetch('/demo/api/users')
                .then(response => response.json())
                .then(data => {
                    const userList = data.map((row: UAMUser) => {
                        return row.name
                    })
                    setOptions(userList);
                })
                .catch(error => console.error('Error fetching users:', error));
        }
    }, [isOpen]);

    const handleClose = () => {
        setIsOpen(false);
    };

    const handleOk = () => {
        if (selectedUser) {
            fetch('/users', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ user: selectedUser }),
            })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(() => {
                    console.log('User successfully added');
                    handleClose();
                })
                .catch(error => console.error('Error adding user:', error));
        } else {
            console.warn('No user selected');
        }
    };

    return (
        <Dialog open={isOpen} onClose={handleClose} fullWidth={true}>
            <DialogTitle>Select a User</DialogTitle>
            <DialogContent>
                <Autocomplete
                    options={options}
                    value={selectedUser}
                    onChange={(_, newValue) => { setSelectedUser(newValue); }}
                    renderInput={(params) => (
                        <TextField {...params} label="User" variant="outlined" fullWidth />
                    )}
                />
            </DialogContent>
            <DialogActions>
                <Button onClick={handleClose} color="primary">
                    Cancel
                </Button>
                <Button onClick={handleOk} color="primary" variant="contained">
                    OK
                </Button>
            </DialogActions>
        </Dialog>
    );
};


export default function UAMGroups() {
    const [loading, setLoading] = useState<boolean>(true);
    const [groupColumns, setGroupColumns] = useState<GridColDef[]>([]);
    const [userColumns, setUserColumns] = useState<GridColDef[]>([]);
    const [groupRows, setGroupRows] = useState<any[]>([]);
    const [leftUserRows, setLeftUserRows] = useState<any[]>([]);
    const [rightUserRows, setRightUserRows] = useState<any[]>([]);
    const [selectedGroup, setSelectedGroup] = useState<UAMGroup>({
        uid: "n/a",
        name: "n/a",
        users: [],
        children: [],
    })
    const [leftSelected, setLeftSelected] = useState<GridRowSelectionModel>([]);
    const [rightSelected, setRightSelected] = useState<GridRowSelectionModel>([]);
    const [sortModel, setSortModel] = React.useState<GridSortModel>([{ field: "name", sort: "asc" }]);
    const [showAddGroup, setShowAddGroup] = useState<boolean>(false);

    useEffect(() => {
        fetch('/demo/api/groups')
            .then(response => response.json())
            .then(jsonData => {
                const data = jsonData.map((row: UAMGroup) => {
                    return {
                        name: row.name,
                        id: row.uid,
                    }
                })
                setGroupRows(data)
                setGroupColumns([
                    { field: 'name', headerName: 'Name', width: 200 },
                    { field: 'date', headerName: 'Date', width: 150 },
                ])
                setLoading(false);
            })
            .catch(error => {
                console.error('Error fetching data:', error);
            });
        fetch(`/demo/api/users`)
            .then(response => response.json())
            .then(jsonData => {
                const data = jsonData.map((row: UAMUser) => {
                    return {
                        name: row.name,
                        id: row.uid,
                    }
                })
                setRightUserRows(data)
                setUserColumns([
                    { field: 'name', headerName: 'Name', width: 200 },
                    { field: 'date', headerName: 'Date', width: 150 },
                ])
                setLoading(false);
            })
            .catch(error => {
                console.error('Error fetching data:', error);
            });
    }, []);


    if (loading) {
        return <CircularProgress />;
    }

    const onOpenCreateGroupDialog = async () => {
        setShowAddGroup(true)
    }

    const handleGroupRowClick: GridEventListener<'rowClick'> = (params) => {
        setSelectedGroup(params.row as UAMGroup)
        fetch(`/demo/api/users/${params.id}`)
            .then(response => response.json())
            .then(jsonData => {
                const data = jsonData.map((row: UAMUser) => {
                    return {
                        name: row.name,
                        id: row.uid,
                    }
                })
                setLeftUserRows(data)
                setUserColumns([
                    { field: 'name', headerName: 'Name', width: 200 },
                    { field: 'date', headerName: 'Date', width: 150 },
                ])
                setLoading(false);
            })
            .catch(error => {
                console.error('Error fetching data:', error);
            });
    };

    const onSelectLeft = (selection: GridRowSelectionModel) => { setLeftSelected(selection); };
    const onSelectRight = (selection: GridRowSelectionModel) => { setRightSelected(selection); };

    const onMoveRightToLeft = () => {
        const itemsToMove = rightUserRows.filter((item) => rightSelected.includes(item.id));
        setRightUserRows(rightUserRows.filter((item) => !rightSelected.includes(item.id)));
        setLeftUserRows([...leftUserRows, ...itemsToMove]);
        setRightSelected([]);
    };

    const onMoveLeftToRight = () => {
        const itemsToMove = leftUserRows.filter((item) => leftSelected.includes(item.id));
        setLeftUserRows(leftUserRows.filter((item) => !leftSelected.includes(item.id)));
        setRightUserRows([...rightUserRows, ...itemsToMove]);
        setLeftSelected([]);
    };

    return (
        <Grid container spacing={2}>
            <Grid size={4} alignItems="left">
                {/* Info Field */}
                <Paper style={{
                    padding: '20px', display: 'flex',
                    flexDirection: 'column',
                }} sx={{ mt: 0, mb: 6 }}>
                    <Title>Group</Title>

                    <Typography variant="subtitle1" gutterBottom>
                        Group: {selectedGroup.name}
                    </Typography>

                    <Grid container size="grow" spacing={2}>
                        <Grid>
                            <Typography variant="subtitle1" gutterBottom>
                                Group: {selectedGroup.name}
                            </Typography>
                        </Grid>
                        <Grid>
                            <Typography variant="subtitle1" gutterBottom>
                                Group: {selectedGroup.name}
                            </Typography>
                        </Grid>
                    </Grid>
                </Paper>

                <Paper style={{ padding: '20px', display: 'flex', flexDirection: 'column', }}>
                    <Title>Groups</Title>
                    <Box height="52.4vh">
                        <DataGrid
                            disableColumnSelector
                            rows={groupRows}
                            columns={groupColumns}
                            slots={{ toolbar: GridToolbar }}
                            onRowClick={handleGroupRowClick}
                            sortModel={sortModel}
                            slotProps={{
                                toolbar: {
                                    showQuickFilter: true,
                                },
                            }}
                        />
                    </Box >
                    <Button variant="contained" color="primary" onClick={onOpenCreateGroupDialog}>Create Group</Button>
                    <ShowAddGroup isOpen={showAddGroup} setIsOpen={setShowAddGroup} />
                </Paper>


            </Grid>
            <Grid size={4} justifyContent="center" alignItems="center">
                <Paper style={{ padding: '20px', display: 'flex', flexDirection: 'column', }}>
                    <Title>Users in {selectedGroup.name}</Title>
                    <Box height="70vh">
                        <DataGrid
                            checkboxSelection
                            disableColumnSelector
                            rows={leftUserRows}
                            columns={userColumns}
                            onRowSelectionModelChange={onSelectLeft}
                            sortModel={sortModel}
                            slots={{ toolbar: GridToolbar }}
                            slotProps={{
                                toolbar: {
                                    showQuickFilter: true,
                                },
                            }}
                        />
                    </Box >
                    <Button variant="contained" color="primary"
                        onClick={onMoveLeftToRight}>Remove from Group</Button>
                </Paper>
            </Grid>
            <Grid size={4} justifyContent="center" alignItems="center">
                <Paper style={{ padding: '20px', display: 'flex', flexDirection: 'column', }}>
                    <Title>Unassigned Users</Title>
                    <Box height="70vh">
                        <DataGrid
                            checkboxSelection
                            disableColumnSelector
                            rows={rightUserRows}
                            columns={userColumns}
                            onRowSelectionModelChange={onSelectRight}
                            sortModel={sortModel}
                            slots={{ toolbar: GridToolbar }}
                            slotProps={{
                                toolbar: {
                                    showQuickFilter: true,
                                },
                            }}
                        />
                    </Box >
                    <Button variant="contained" color="primary" onClick={onMoveRightToLeft}>Add to Group</Button>
                </Paper>
            </Grid>

        </Grid>
    );
};
