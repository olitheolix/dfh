import React from 'react';
import { useState, useEffect } from 'react';
import Box from '@mui/material/Box';
import Grid from '@mui/material/Grid2';
import { DataGrid, GridEventListener } from '@mui/x-data-grid';
import { GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import { CircularProgress, Button } from '@mui/material';
import { GridToolbar } from '@mui/x-data-grid';
import {
    Paper, Typography, Dialog, DialogTitle, DialogContent, DialogActions,
    Autocomplete, TextField,
} from '@mui/material';
import { UAMUser, UAMGroup } from './UAMInterfaces'

import Title from './Title';


function ShowAddUser({ isOpen, setIsOpen }: { isOpen: boolean, setIsOpen: React.Dispatch<React.SetStateAction<boolean>> }) {
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
                    onChange={(event, newValue) => {
                        setSelectedUser(newValue);
                    }}
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
    const [groupRows, setGroupRows] = useState<any[]>([]);
    const [groupColumns, setGroupColumns] = useState<GridColDef[]>([]);
    const [groupUserRows, setGroupUserRows] = useState<any[]>([]);
    const [otherUserRows, setOtherUserRows] = useState<any[]>([]);
    const [userColumns, setUserColumns] = useState<GridColDef[]>([]);
    const [isUseraddModalOpen, setIsUseraddModalOpen] = useState<boolean>(false);
    const [selectedGroup, setSelectedGroup] = useState<UAMGroup>({
        uid: "n/a",
        name: "n/a",
        users: [],
        children: [],
    })
    const [selectedItems, setSelectedItems] = useState<GridRowSelectionModel>([]);

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
                console.error('Error fetching data:');
            });
    }, []);


    if (loading) {
        return <CircularProgress />;
    }

    const onOpenUserAddDialog = async () => {
        setIsUseraddModalOpen(true)
    }

    const handleGroupRowClick: GridEventListener<'rowClick'> = (params) => {
        console.log(params)
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
                setGroupUserRows(data)
                setUserColumns([
                    { field: 'name', headerName: 'Name', width: 200 },
                    { field: 'date', headerName: 'Date', width: 150 },
                ])
                setLoading(false);
            })
            .catch(error => {
                console.error('Error fetching data:');
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
                setOtherUserRows(data)
                setUserColumns([
                    { field: 'name', headerName: 'Name', width: 200 },
                    { field: 'date', headerName: 'Date', width: 150 },
                ])
                setLoading(false);
            })
            .catch(error => {
                console.error('Error fetching data:');
            });
    };

    const handleSelectionChange = (selectionModel: GridRowSelectionModel) => {
        setSelectedItems(selectionModel);
    };

    const handleMoveItems = () => {
        const itemsToMove = otherUserRows.filter((item) => selectedItems.includes(item.id));
        setOtherUserRows(otherUserRows.filter((item) => !selectedItems.includes(item.id)));
        setGroupUserRows([...groupUserRows, ...itemsToMove]);
        setSelectedItems([]);
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
                            <Button variant="contained" color="primary" disabled={true}
                                onClick={onOpenUserAddDialog}>Add User</Button>
                            <ShowAddUser isOpen={isUseraddModalOpen} setIsOpen={setIsUseraddModalOpen} />
                        </Grid>
                        <Grid>
                            <Button variant="contained" color="primary" disabled={true}
                                onClick={onOpenUserAddDialog}>Add Group</Button>
                            <ShowAddUser isOpen={isUseraddModalOpen} setIsOpen={setIsUseraddModalOpen} />

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
                            slotProps={{
                                toolbar: {
                                    showQuickFilter: true,
                                },
                            }}
                        />
                    </Box >
                </Paper>


            </Grid>
            <Grid size={4} justifyContent="center" alignItems="center">
                <Paper style={{ padding: '20px', display: 'flex', flexDirection: 'column', }}>
                    <Title>Users in {selectedGroup.name}</Title>
                    <Box height="70vh">
                        <DataGrid
                            checkboxSelection
                            disableColumnSelector
                            rows={groupUserRows}
                            columns={userColumns}
                            slots={{ toolbar: GridToolbar }}
                            slotProps={{
                                toolbar: {
                                    showQuickFilter: true,
                                },
                            }}
                        />
                    </Box >
                    <Button variant="contained" color="primary"
                        onClick={onOpenUserAddDialog}>Remove from Group</Button>
                </Paper>
            </Grid>
            <Grid size={4} justifyContent="center" alignItems="center">
                <Paper style={{ padding: '20px', display: 'flex', flexDirection: 'column', }}>
                    <Title>Unassigned Users</Title>
                    <Box height="70vh">
                        <DataGrid
                            checkboxSelection
                            disableColumnSelector
                            rows={otherUserRows}
                            columns={userColumns}
                            onRowSelectionModelChange={handleSelectionChange}
                            slots={{ toolbar: GridToolbar }}
                            slotProps={{
                                toolbar: {
                                    showQuickFilter: true,
                                },
                            }}
                        />
                    </Box >
                    <Button variant="contained" color="primary"
                        onClick={handleMoveItems}>Add to Group</Button>
                </Paper>
            </Grid>

        </Grid>
    );
};
