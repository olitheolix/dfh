import React from 'react';
import { useState, useEffect } from 'react';
import Box from '@mui/material/Box';
import { SimpleTreeView } from '@mui/x-tree-view/SimpleTreeView';
import { TreeItem } from '@mui/x-tree-view/TreeItem';
import Grid from '@mui/material/Grid2';
import { DataGrid } from '@mui/x-data-grid';
import { GridColDef } from '@mui/x-data-grid';
import { CircularProgress, Button } from '@mui/material';
import { GridToolbar } from '@mui/x-data-grid';
import {
    Paper, Typography, Dialog, DialogTitle, DialogContent, DialogActions,
    MenuItem, Select, Autocomplete, TextField,
} from '@mui/material';

import Title from './Title';


interface TreeNode {
    id: string;
    elId: 'group' | 'user'
    label: string;
    children?: TreeNode[]; // Recursive type to handle nested children
}

interface User {
    name: string;
    uid: string
}

function ShowAddUser({ isOpen, setIsOpen }: { isOpen: boolean, setIsOpen: React.Dispatch<React.SetStateAction<boolean>> }) {
    const [options, setOptions] = useState<string[]>([]);
    const [selectedUser, setSelectedUser] = useState<string | null>(null);

    useEffect(() => {
        // Fetch the list of users from the /users endpoint when the dialog opens
        if (isOpen) {
            fetch('/demo/api/user')
                .then(response => response.json())
                .then(data => {
                    const userList = data.map((row: User) => {
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


export default function UAMOverview() {
    const [treeData, setTreeData] = useState<TreeNode[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [dataGridRows, setDataGridRows] = useState<any[]>([]);
    const [columns, setColumns] = useState<GridColDef[]>([]);
    const [isUseraddModalOpen, setIsUseraddModalOpen] = useState<boolean>(false);
    const [selectedNode, setSelectedNode] = useState<string>("");

    useEffect(() => {
        fetch('/demo/api/tree')
            .then(response => response.json())
            .then(jsonData => {
                setTreeData(jsonData);
                setLoading(false);
            })
            .catch(error => {
                console.error('Error fetching data:');
            });
    }, []);

    // Sample data for DataGrid
    const rows = [
        { id: 1, col1: 'Hello', col2: 'World' },
        { id: 2, col1: 'DataGrid', col2: 'Component' },
        { id: 3, col1: 'Material-UI', col2: 'Rocks' },
    ];

    const columnsold = [
        { field: 'col1', headerName: 'Column 1', width: 150 },
        { field: 'col2', headerName: 'Column 2', width: 150 },
    ];

    // const [rows, setRows] = useState<GridRowsProp>([]);

    const handleNodeSelect = (node: TreeNode) => {
        fetch('/demo/api/user')
            .then(response => response.json())
            .then(data => {
                const dataWithID = data.map((row: User) => {
                    return {
                        name: row.name,
                        id: row.uid
                    }
                })
                setDataGridRows(dataWithID);
                setColumns([
                    { field: 'name', headerName: 'Name', width: 200 },
                    { field: 'date', headerName: 'Date', width: 150 },
                ]);
                setSelectedNode(node.label)
            })
            .catch(error => {
                console.error('Error fetching data:', error);
            });
    };


    // Recursive function to render tree items
    const renderTree = (nodes: TreeNode) => (
        < TreeItem key={nodes.label} itemId={nodes.label} label={nodes.label} onClick={() => handleNodeSelect(nodes)
        }>
            {
                Array.isArray(nodes.children)
                    ? nodes.children.map((node: TreeNode) => renderTree(node))
                    : null
            }
        </TreeItem >
    );

    if (loading) {
        return <CircularProgress />;
    }

    const onOpenUserAddDialog = async () => {
        setIsUseraddModalOpen(true)
    }

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
                        Group: {selectedNode}
                    </Typography>

                    <Grid container size="grow" spacing={2}>
                        <Grid>
                            <Button variant="contained" color="primary"
                                onClick={onOpenUserAddDialog}>Add User</Button>
                            <ShowAddUser isOpen={isUseraddModalOpen} setIsOpen={setIsUseraddModalOpen} />

                        </Grid>
                        <Grid>
                            <Button variant="contained" color="primary"
                                onClick={onOpenUserAddDialog}>Add Group</Button>
                            <ShowAddUser isOpen={isUseraddModalOpen} setIsOpen={setIsUseraddModalOpen} />

                        </Grid>
                    </Grid>
                </Paper>

                {/* TreeView section */}
                {loading ? (
                    <p>Loading...</p>
                ) : error ? (
                    <p>{error}</p>
                ) : (
                    <SimpleTreeView
                        defaultSelectedItems={treeData.length > 0 ? treeData[0].label : null}
                    >
                        {treeData.map((node) => renderTree(node))}

                    </SimpleTreeView>
                )}

            </Grid>
            <Grid size={7} justifyContent="center" alignItems="center">
                <Paper style={{ padding: '20px', display: 'flex', flexDirection: 'column', }}>
                    <Title>Users in {selectedNode}</Title>
                    <Box height="70vh">
                        <DataGrid
                            disableColumnSelector
                            rows={dataGridRows}
                            columns={columns}
                            slots={{ toolbar: GridToolbar }}
                            slotProps={{
                                toolbar: {
                                    showQuickFilter: true,
                                },
                            }}
                        />
                    </Box >
                </Paper>

            </Grid>
        </Grid>
    );
};
