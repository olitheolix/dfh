import { Button, TextField, Grid } from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import ControlPointIcon from '@mui/icons-material/ControlPoint';

import { K8sEnvVar } from './BackendInterfaces'


export interface EnvVarTableIfx {
    pairs: K8sEnvVar[];
    setPairs: React.Dispatch<React.SetStateAction<K8sEnvVar[]>>;
}


export default function EnvVarTable({ pairs, setPairs }: EnvVarTableIfx) {
    const handleAddRow = () => {
        setPairs([...pairs, { name: '', value: '', valueFrom: null }]);
    };

    const handleRemoveRow = (index: number) => {
        const updatedPairs = [...pairs];
        updatedPairs.splice(index, 1);
        setPairs(updatedPairs);
    };

    const handleChange = (index: number, field: 'name' | 'value', value: string) => {
        const updatedPairs: K8sEnvVar[] = [...pairs];
        updatedPairs[index][field] = value;
        setPairs(updatedPairs);
    };

    return (
        <div>
            {pairs.map((pair, index) => (
                <Grid container key={index} spacing={2} alignItems="center">
                    <Grid item xs={4}>
                        <TextField
                            label="Key"
                            variant="standard"
                            fullWidth
                            value={pair.name}
                            onChange={(e) => handleChange(index, 'name', e.target.value)}
                        />
                    </Grid>
                    <Grid item xs={4}>
                        <TextField
                            label="Value"
                            variant="standard"
                            fullWidth
                            value={pair.value}
                            onChange={(e) => handleChange(index, 'value', e.target.value)}
                        />
                    </Grid>
                    <Grid item>
                        <Button variant="text" color="primary" onClick={() => handleRemoveRow(index)} startIcon={<DeleteIcon />}>
                            Delete
                        </Button>
                    </Grid>
                </Grid>
            ))}
            <Button variant="text" color="primary" onClick={handleAddRow} startIcon={<ControlPointIcon />}>
                Add Row
            </Button>
        </div>
    );
}
